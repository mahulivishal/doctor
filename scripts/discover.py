"""
discover.py — Phase 2: Discover all endpoints per service, filter to targets.
Uses Anthropic SDK directly for token tracking.
"""
import json
import os
import re
from typing import List, Optional
import subprocess

from config import Config, TargetEndpoint
from token_tracker import tracker

DISCOVERY_PROMPT = """You are analyzing the '{svc_name}' service codebase.

STEP 1 — Detect language and framework by reading:
  pom.xml / build.gradle / build.gradle.kts  → Java/Kotlin Spring Boot
  requirements.txt / pyproject.toml          → Python Flask/FastAPI/Django
  go.mod                                     → Go (Gin/Echo/Chi/Fiber/net-http)
  package.json                               → Node Express/Fastify/NestJS

STEP 2 — Find EVERY HTTP endpoint using these patterns:

  Java/Kotlin Spring Boot:
    @RestController, @GetMapping, @PostMapping, @PutMapping,
    @PatchMapping, @DeleteMapping, @RequestMapping(method=...)

  Python Flask:
    @app.route('/path', methods=['GET',...])
    @blueprint.route(...)

  Python FastAPI:
    @app.get, @app.post, @app.put, @app.patch, @app.delete
    @router.get, @router.post, etc.

  Go:
    Gin:   r.GET, r.POST, r.PUT, r.PATCH, r.DELETE, r.Group
    Echo:  e.GET, e.POST, e.PUT, e.PATCH, e.DELETE, e.Group
    Chi:   r.Get, r.Post, r.Put, r.Patch, r.Delete, r.Route, r.Group
    Fiber: app.Get, app.Post, app.Put, app.Patch, app.Delete
    net/http: http.HandleFunc, http.Handle, mux.Handle

  Node Express/NestJS:
    app.get, app.post, router.get, router.post
    @Get, @Post, @Put, @Patch, @Delete (NestJS decorators)

STEP 3 — Read every controller/handler/router file found.

Return ONLY raw JSON — no markdown, no explanation:

{{
  "service": "{svc_name}",
  "language": "Java|Kotlin|Python|Go|TypeScript|JavaScript",
  "framework": "Spring Boot|FastAPI|Flask|Gin|Echo|Chi|Fiber|Express|NestJS",
  "discovery_notes": "brief structural note",
  "endpoints": [
    {{
      "id": "{svc_name}_GET_path_slugified",
      "service": "{svc_name}",
      "service_path": "{svc_path}",
      "method": "GET",
      "path": "/api/v1/resource/{{id}}",
      "handler_file": "relative/path/to/Handler.java",
      "handler_function": "functionName",
      "middleware": [],
      "auth_required": false,
      "notes": ""
    }}
  ]
}}"""


def _normalize_path(path: str) -> str:
    path = re.sub(r'\{([^}:]+):[^}]+\}', r'{\1}', path)
    path = re.sub(r'\{[^}]+\}', '{P}', path)
    path = re.sub(r':[^/]+',    '{P}', path)
    return path.rstrip('/')


def _slugify(s: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_-]', '_', s).strip('_')


def _parse_json(output: str) -> Optional[dict]:
    for fn in [
        lambda o: json.loads(o),
        lambda o: json.loads(re.search(r'```(?:json)?\s*(\{.*?\})\s*```', o, re.DOTALL).group(1)),
        lambda o: json.loads(re.search(r'(\{.*\})', o, re.DOTALL).group(1)),
    ]:
        try:
            return fn(output)
        except Exception:
            continue
    return None


def _read_files(svc_path: str) -> str:
    """Build a file listing for the prompt context."""
    files = []
    for root, dirs, filenames in os.walk(svc_path):
        # Skip noise dirs
        dirs[:] = [d for d in dirs if d not in (
            'node_modules', '.git', 'dist', 'build', '__pycache__',
            'target', '.gradle', 'venv', '.venv', 'coverage'
        )]
        for fname in filenames:
            rel = os.path.relpath(os.path.join(root, fname), svc_path)
            files.append(rel)
    return "\n".join(sorted(files)[:500])  # cap at 500 files


def discover_service(cfg: Config, svc) -> List[dict]:
    print(f"   📡 Discovering: {svc.name} ({svc.path})")

    if not os.path.isdir(svc.path):
        print(f"   ⚠️  Path not found: {svc.path} — skipping")
        return []

    # Read actual files from disk so Claude knows what's available
    file_listing = _read_files(svc.path)

    prompt = DISCOVERY_PROMPT.format(
        svc_name=svc.name,
        svc_path=svc.path,
    ) + f"\n\nFile listing for reference:\n{file_listing}"

    try:
        if cfg.api_key:
            import anthropic
            client = anthropic.Anthropic(api_key=cfg.api_key)
            response = client.messages.create(
                model=cfg.claude_model,
                max_tokens=4096,
                tools=[
                    {"name": "Read",  "description": "Read a file",          "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
                    {"name": "Glob",  "description": "List files by pattern", "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}},
                    {"name": "Grep",  "description": "Search file contents",  "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}}, "required": ["pattern"]}},
                ],
                messages=[{"role": "user", "content": prompt}],
            )
            tracker.add(response.usage.input_tokens, response.usage.output_tokens)
            output = "".join(b.text for b in response.content if hasattr(b, "text"))
        else:
            result = subprocess.run(
                [cfg.claude_bin, "-p", prompt,
                 "--allowedTools", "Read,Glob,Grep"],
                capture_output=True,
                text=True,
                cwd=svc.path,
            )
            output = result.stdout + result.stderr

    except Exception as e:
        print(f"   ⚠️  Error for {svc.name}: {e}")
        return []

    data = _parse_json(output)
    if not data:
        print(f"   ⚠️  Could not parse discovery output for {svc.name}")
        print(f"       Raw (first 300): {output[:300]}")
        return []

    endpoints = data.get("endpoints", [])
    lang = data.get("language", "unknown")
    fw   = data.get("framework", "unknown")

    for ep in endpoints:
        ep["service"]      = svc.name
        ep["service_path"] = svc.path
        raw_id = ep.get("id", f"{svc.name}_{ep.get('method','')}_{ep.get('path','')}")
        ep["id"] = _slugify(raw_id)

    print(f"   ✓  {svc.name}: {len(endpoints)} endpoints ({lang} / {fw})")
    return endpoints


def filter_endpoints(all_endpoints, targets):
    if not targets:
        return all_endpoints, []

    target_map = {}
    for t in targets:
        key = (_normalize_path(t.path), t.service_name)
        target_map[key] = t

    kept, missed = [], []
    for ep in all_endpoints:
        norm   = _normalize_path(ep["path"])
        ep_svc = ep.get("service")
        match  = target_map.get((norm, ep_svc)) or target_map.get((norm, None))
        if not match:
            continue
        if match.method.upper() not in ("ANY", ep.get("method", "").upper()):
            continue
        ep["acl_priority"] = match.acl_priority
        ep["label"]        = match.label
        kept.append(ep)

    for t in targets:
        if not any(_normalize_path(ep["path"]) == _normalize_path(t.path) for ep in kept):
            missed.append(t.path)

    return kept, missed


def run(cfg: Config) -> List[dict]:
    print()
    all_endpoints = []
    for svc in cfg.services:
        endpoints = discover_service(cfg, svc)
        all_endpoints.extend(endpoints)

    print(f"\n   Total discovered: {len(all_endpoints)} endpoints")

    filtered, missed = filter_endpoints(all_endpoints, cfg.target_endpoints)

    manifest_path = os.path.join(cfg.manifests_dir, f"{cfg.service}-manifest.json")
    with open(manifest_path, "w") as f:
        json.dump({
            "service":       cfg.service,
            "endpoints":     filtered,
            "total_found":   len(all_endpoints),
            "matched_count": len(filtered),
        }, f, indent=2)

    print(f"   Matched/targeted: {len(filtered)} endpoints")
    print()
    print("📋 Endpoints queued for analysis:")
    for ep in filtered:
        label = f" ({ep['label']})" if ep.get("label") else ""
        print(f"   [{ep['service']}] {ep['method']:6} {ep['path']}{label}")

    if missed:
        print()
        print("⚠️  Target paths NOT matched in repo:")
        for p in missed: print(f"   ✗ {p}")
        print("\n   All discovered paths:")
        for ep in all_endpoints:
            print(f"   [{ep['service']}] {ep['method']:6} {ep['path']}")

    return filtered