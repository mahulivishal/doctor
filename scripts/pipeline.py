#!/usr/bin/env python3
"""
pipeline.py — Master orchestrator for Doctor.
Supports three invocation modes:
  Terminal:  bash run.sh → python3 scripts/pipeline.py [args]
  API:       server.py calls run_discover/run_analyze/run_artifacts directly
  SKILL:     Claude Code reads SKILL.md → runs bash run.sh

Usage (Terminal / SKILL):
  python3 scripts/pipeline.py                   # full run
  python3 scripts/pipeline.py --from 3          # resume from phase 3
  python3 scripts/pipeline.py --only 2          # discovery only
  python3 scripts/pipeline.py --api <id>        # single endpoint
  python3 scripts/pipeline.py --run-id <id>     # use existing run workspace
  python3 scripts/pipeline.py --raise-pr        # raise PR after generation
"""
import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

import config as cfg_module
from config import SKIP_OPTIONS
import clone as clone_module
import discover
import analyze
import render
import artifacts
from token_tracker import tracker


# ─── Phase functions (used by both terminal and server) ───────────────────────

def run_discover(cfg, reporter=None) -> list:
    """Phase 2 — discovery. Returns endpoint list."""
    if reporter:
        reporter.set_phase(2, "Discovering endpoints")
    print("━" * 50)
    print(f" Phase 2: Discovery — {cfg.service}")
    print("━" * 50)
    endpoints = discover.run(cfg)
    if not endpoints:
        raise RuntimeError("No endpoints matched. Check target-endpoints.yaml")
    return endpoints


def run_analyze(cfg, endpoints, target_id="", reporter=None) -> dict:
    """Phase 3 — analysis. Returns result dict."""
    if reporter:
        reporter.set_phase(3, "Analyzing endpoints")
        reporter.set_endpoints(len(endpoints))
    print("━" * 50)
    print(f" Phase 3: Analysis — {cfg.service}")
    print("━" * 50)
    result = analyze.run(cfg, endpoints, target_id=target_id)
    print(f"\n✅ Phase 3 complete — Done: {result['done']} | Failed: {result['failed']}")
    if result["failed"] > 0:
        print(f"⚠️  {result['failed']} endpoint(s) failed. Re-run with --from 3 to retry.")
    return result


def run_render(cfg, target_id="", reporter=None) -> dict:
    """Phase 4 — render docs."""
    if reporter:
        reporter.set_phase(4, "Rendering documentation")
    print("━" * 50)
    print(f" Phase 4: Render — {cfg.service}")
    print("━" * 50)
    result = render.run(cfg, target_id=target_id)
    print(f"✅ Rendered {result['done']} documents")
    return result


def run_artifacts(cfg, reporter=None) -> None:
    """Phase 5 — generate artifacts."""
    if reporter:
        reporter.set_phase(5, "Generating artifacts")
    print("━" * 50)
    print(f" Phase 5: Artifacts — {cfg.service}")
    print("━" * 50)
    artifacts.run(cfg)


# ─── Terminal / SKILL arg parsing ─────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="Doctor — API documentation pipeline")
    parser.add_argument("--from",      dest="from_phase", type=int, default=1)
    parser.add_argument("--only",      dest="only_phase", type=int, default=0)
    parser.add_argument("--no-reset",  action="store_true")
    parser.add_argument("--api",       dest="target_api", default="",
                        help="Re-run a single endpoint by ID")
    parser.add_argument("--run-id",    dest="run_id", default=None,
                        help="Use an existing run workspace instead of creating a new one")
    parser.add_argument("--raise-pr",  action="store_true",
                        help="Raise a PR after successful generation (requires VCS token)")
    parser.add_argument("--skip",      dest="skip", action="append", default=[],
                        metavar="ARTIFACT",
                        help="Skip an artifact: " + "|".join(SKIP_OPTIONS.keys()))
    return parser.parse_args()


# ─── Reset ────────────────────────────────────────────────────────────────────

def reset(cfg):
    print("🧹 Resetting workspace...")
    dirs_to_clear = [
        cfg.manifests_dir, cfg.analysis_dir, cfg.docs_dir,
        cfg.data_model_dir, cfg.db_er_dir, cfg.postman_dir, cfg.api_doc_dir,
    ]
    for d in dirs_to_clear:
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d, exist_ok=True)
    print("✅ Workspace clean\n")


# ─── Manifest loader ──────────────────────────────────────────────────────────

def load_manifest(cfg) -> list:
    manifest_path = os.path.join(cfg.manifests_dir, f"{cfg.service}-manifest.json")
    if not os.path.exists(manifest_path):
        print(f"❌ Manifest not found: {manifest_path}")
        print("   Run Phase 2 first: python3 scripts/pipeline.py --only 2")
        sys.exit(1)
    with open(manifest_path) as f:
        return json.load(f).get("endpoints", [])


# ─── Main (Terminal / SKILL) ──────────────────────────────────────────────────

def main():
    args  = parse_args()
    start = time.time()

    # Validate skip options
    invalid = [s for s in args.skip if s not in SKIP_OPTIONS]
    if invalid:
        print(f"❌ Unknown --skip value(s): {invalid}")
        print(f"   Valid: {list(SKIP_OPTIONS.keys())}")
        sys.exit(1)

    skip = set(args.skip)
    if skip:
        print(f"⏭  Skipping: {', '.join(skip)}")

    # Override raise_pr from CLI flag
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = cfg_module.load(project_root, skip=skip, run_id=args.run_id)

    # CLI --raise-pr overrides .env RAISE_PR
    if args.raise_pr:
        cfg = cfg.__class__(**{**cfg.__dict__, "raise_pr": True})

    print()
    print("╔══════════════════════════════════════════════╗")
    print(f"║  Doctor  ·  {cfg.service:<26}  ·  {cfg.run_id} ║")
    print("╚══════════════════════════════════════════════╝")
    print()

    cloned_in_this_run = False

    # ── Single endpoint mode ───────────────────────────────────────────────
    if args.target_api:
        print(f"🎯 Single-endpoint mode: {args.target_api}")
        endpoints = load_manifest(cfg)
        run_analyze(cfg, endpoints, target_id=args.target_api)
        if "docs" not in skip:
            run_render(cfg, target_id=args.target_api)
        print()
        print(tracker.summary())
        return

    # ── Phase control ──────────────────────────────────────────────────────
    do_reset = (
        not args.no_reset
        and args.from_phase == 1
        and args.only_phase == 0
    )
    if do_reset:
        reset(cfg)

    def should_run(phase: int) -> bool:
        if args.only_phase:
            return phase == args.only_phase
        return phase >= args.from_phase

    endpoints = None

    if should_run(1):
        print("━" * 50)
        print(f" Phase 1: Clone")
        print("━" * 50)
        cloned_in_this_run = clone_module.run(cfg)
        print()

    if should_run(2):
        endpoints = run_discover(cfg)
        print()

    if should_run(3):
        if endpoints is None:
            endpoints = load_manifest(cfg)
        run_analyze(cfg, endpoints)
        print()

    if should_run(4) and "docs" not in skip:
        run_render(cfg)
        print()

    if should_run(5):
        run_artifacts(cfg)
        print()

    # ── PR ─────────────────────────────────────────────────────────────────
    if cfg.raise_pr:
        if cloned_in_this_run:
            import asyncio
            import pr as pr_module
            branch_name = (
                f"doctor/{cfg.service}"
                f"-{datetime.utcnow().strftime('%Y%m%d')}"
                f"-{cfg.run_id}"
            )
            clone_module.create_pr_branch(cfg, branch_name)
            ep_list = endpoints or load_manifest(cfg)
            pr_url  = asyncio.run(pr_module.raise_pr(cfg, branch_name, ep_list))
            print(f"\n🔀 PR: {pr_url}")
        else:
            print("\n⏭  PR skipped — repo was not cloned in this run (use --from 1 to re-clone)")

    # ── Summary ────────────────────────────────────────────────────────────
    elapsed = time.time() - start
    mins, secs = divmod(int(elapsed), 60)

    def _count(d, ext):
        return len([f for f in os.listdir(d) if f.endswith(ext)]) \
               if os.path.exists(d) else 0

    print(f"\n⏱  Total time: {mins}m {secs}s")
    print(f"   Run ID: {cfg.run_id}")
    print(f"   Workspace: workspace/runs/{cfg.run_id}/")
    if "docs"      not in skip: print(f"   documents/           → {_count(cfg.docs_dir, '.md')} docs")
    if "datamodel" not in skip: print(f"   data_model/          → {_count(cfg.data_model_dir, '.md')} diagrams")
    if "er"        not in skip: print(f"   db_entity_relations/ → {_count(cfg.db_er_dir, '.md')} ER diagram(s)")
    if "postman"   not in skip: print(f"   postman_collection/  → {_count(cfg.postman_dir, '.json')} collection(s)")
    if "swagger"   not in skip: print(f"   api_document/        → {_count(cfg.api_doc_dir, '.yaml')} OpenAPI spec(s)")
    print()
    print(tracker.summary())


if __name__ == "__main__":
    main()
