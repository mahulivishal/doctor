#!/usr/bin/env python3
"""
pipeline.py — Master orchestrator for api-doc-forge.
Replaces all individual bash scripts. Called by run.sh.

Usage:
  python3 scripts/pipeline.py                  # full reset + run
  python3 scripts/pipeline.py --from 3         # resume from phase 3
  python3 scripts/pipeline.py --only 2         # run only discovery
  python3 scripts/pipeline.py --no-reset       # skip reset, full run
  python3 scripts/pipeline.py --api <id>       # re-run one endpoint
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time

# Add scripts dir to path so modules can import each other
sys.path.insert(0, os.path.dirname(__file__))

import config as cfg_module
from config import SKIP_OPTIONS
import discover
import analyze
import render
import artifacts
from token_tracker import tracker


def parse_args():
    parser = argparse.ArgumentParser(description="Doctor — API documentation pipeline")
    parser.add_argument("--from",     dest="from_phase", type=int, default=1,
                        help="Start from phase N (skips reset)")
    parser.add_argument("--only",     dest="only_phase", type=int, default=0,
                        help="Run only phase N")
    parser.add_argument("--no-reset", action="store_true",
                        help="Skip workspace reset")
    parser.add_argument("--api",      dest="target_api", default="",
                        help="Re-run a single endpoint by ID")
    parser.add_argument("--skip",     dest="skip", action="append", default=[],
                        metavar="ARTIFACT",
                        help=(
                            "Skip an output artifact. Repeatable. Options:\n" +
                            "\n".join(f"  {k}: {v}" for k, v in SKIP_OPTIONS.items())
                        ))
    return parser.parse_args()


def reset(cfg):
    """Clear all generated files, keep cloned repo and config."""
    print("🧹 Resetting workspace...")
    dirs_to_clear = [
        os.path.join(cfg.manifests_dir,  "*"),
        os.path.join(cfg.analysis_dir,   "*"),
        os.path.join(cfg.docs_dir,       "*"),
        os.path.join(cfg.data_model_dir, "*"),
        os.path.join(cfg.db_er_dir,      "*"),
        os.path.join(cfg.postman_dir,    "*"),
        os.path.join(cfg.api_doc_dir,    "*"),
    ]

    for pattern in dirs_to_clear:
        for f in glob.glob(pattern):
            if os.path.isfile(f):   os.remove(f)
            elif os.path.isdir(f):  shutil.rmtree(f)

    for d in [cfg.manifests_dir, cfg.analysis_dir, cfg.docs_dir,
              cfg.data_model_dir, cfg.db_er_dir, cfg.postman_dir, cfg.api_doc_dir]:
        os.makedirs(d, exist_ok=True)

    print("✅ Workspace clean\n")


def phase1_clone(cfg):
    """Clone repo using the existing bash script (git operations stay in bash)."""
    script = os.path.join(os.path.dirname(__file__), "1-clone-repo.sh")
    if not os.path.exists(script):
        print("⚠️  1-clone-repo.sh not found — skipping clone")
        return
    result = subprocess.run(["bash", script], cwd=cfg.project_root)
    if result.returncode != 0:
        print("❌ Clone failed")
        sys.exit(1)


def phase2_discover(cfg):
    print("━" * 50)
    print(f" Phase 1b: Discovery + Filtering — {cfg.service}")
    print("━" * 50)
    endpoints = discover.run(cfg)
    if not endpoints:
        print("❌ No endpoints matched. Check target-endpoints.yaml")
        sys.exit(1)
    return endpoints


def phase3_analyze(cfg, endpoints, target_api=""):
    print("━" * 50)
    print(f" Phase 2: Deep Analysis — {cfg.service}")
    print("━" * 50)
    result = analyze.run(cfg, endpoints, target_id=target_api)
    print()
    print("━" * 50)
    print(f"✅ Phase 2 complete")
    print(f"   Done: {result['done']} | Failed: {result['failed']}")
    print("━" * 50)
    if result["failed"] > 0:
        print(f"\n⚠️  {result['failed']} endpoint(s) failed. "
              f"Re-run with --from 2 to retry.\n")


def phase4_render(cfg, target_api=""):
    print("━" * 50)
    print(f" Phase 3: Rendering documentation")
    print("━" * 50)
    result = render.run(cfg, target_id=target_api)
    print()
    print(f"✅ Rendered {result['done']} documents → {cfg.docs_dir}/")
    if result["errors"]:
        print(f"❌ {result['errors']} error(s)")


def phase5_artifacts(cfg):
    print("━" * 50)
    print(f" Phase 5: Generating artifacts (Postman, Mermaid, ER, OpenAPI)")
    print("━" * 50)
    artifacts.run(cfg)


def load_manifest(cfg) -> list:
    """Load endpoints from existing manifest file."""
    manifest_path = os.path.join(
        cfg.manifests_dir, f"{cfg.service}-manifest.json"
    )
    if not os.path.exists(manifest_path):
        print(f"❌ Manifest not found: {manifest_path}")
        print("   Run Phase 2 first: python3 scripts/pipeline.py --only 2")
        sys.exit(1)
    with open(manifest_path) as f:
        data = json.load(f)
    return data.get("endpoints", [])


def main():
    args = parse_args()
    start = time.time()

    # Validate skip options
    invalid_skips = [s for s in args.skip if s not in SKIP_OPTIONS]
    if invalid_skips:
        print(f"❌ Unknown --skip value(s): {invalid_skips}")
        print(f"   Valid options: {list(SKIP_OPTIONS.keys())}")
        sys.exit(1)

    skip = set(args.skip)
    if skip:
        print(f"⏭  Skipping: {', '.join(skip)}")

    # Load config
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = cfg_module.load(project_root, skip=skip)

    print()
    print("╔══════════════════════════════════════════════╗")
    print(f"║  Doctor  ·  {cfg.service:<30} ║")
    print("╚══════════════════════════════════════════════╝")
    print()

    # ── Single endpoint mode ──────────────────────────────────────────────
    if args.target_api:
        print(f"🎯 Single-endpoint mode: {args.target_api}")
        endpoints = load_manifest(cfg)
        phase3_analyze(cfg, endpoints, target_api=args.target_api)
        if "docs" not in skip:
            phase4_render(cfg, target_api=args.target_api)
        print()
        print(tracker.summary())
        return

    # ── Determine reset ───────────────────────────────────────────────────
    do_reset = (
        not args.no_reset
        and args.from_phase == 1
        and args.only_phase == 0
    )
    if do_reset:
        reset(cfg)

    # ── Phase execution ───────────────────────────────────────────────────
    def should_run(phase: int) -> bool:
        if args.only_phase:
            return phase == args.only_phase
        return phase >= args.from_phase

    endpoints = None

    if should_run(1):
        phase1_clone(cfg)
        print()

    if should_run(2):
        endpoints = phase2_discover(cfg)
        print()

    if should_run(3):
        if endpoints is None:
            endpoints = load_manifest(cfg)
        phase3_analyze(cfg, endpoints)
        print()

    if should_run(4) and "docs" not in skip:
        phase4_render(cfg)
        print()

    if should_run(5):
        phase5_artifacts(cfg)
        print()

    # ── Summary ───────────────────────────────────────────────────────────
    elapsed = time.time() - start
    mins, secs = divmod(int(elapsed), 60)

    def _count(d, ext):
        return len([f for f in os.listdir(d) if f.endswith(ext)]) if os.path.exists(d) else 0

    print(f"\n⏱  Total time: {mins}m {secs}s")
    if "docs"      not in skip: print(f"   output/documents/           → {_count(cfg.docs_dir, '.md')} API docs")
    if "datamodel" not in skip: print(f"   output/data_model/          → {_count(cfg.data_model_dir, '.md')} class diagrams")
    if "er"        not in skip: print(f"   output/db_entity_relations/ → {_count(cfg.db_er_dir, '.md')} ER diagram(s)")
    if "postman"   not in skip: print(f"   output/postman_collection/  → {_count(cfg.postman_dir, '.json')} collection(s)")
    if "swagger"   not in skip: print(f"   output/api_document/        → {_count(cfg.api_doc_dir, '.yaml')} OpenAPI spec(s)")
    print()
    print(tracker.summary())


if __name__ == "__main__":
    main()