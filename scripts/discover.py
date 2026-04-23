"""
discover.py — Phase 1b: Discover all endpoints per service, filter to targets.
"""
import json
import os
import re
import subprocess
from typing import List, Dict, Optional
from config import Config, TargetEndpoint


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
    """Normalize path params to {P} for matching.
    Handles: {id}, {id:.+}, {id:[0-9]+}, :id
    """
    # Strip Spring/regex patterns inside braces e.g. {param:.+} → {param}
    path = re.sub(r'\{([^}:]+):[^}]+\}', r'{\1}', path)
    # Replace all remaining {param} and :param with {P}
    path = re.sub(r'\{[^}]+\}', '{P}', path)
    path = re.sub(r':[^/]+',    '{P}', path)
    return path.rstrip('/')


def _parse_claude_json(output: str) -> Optional[dict]:
    """Try multiple strategies to extract JSON from Claude's output."""
    strategies = [
        lambda o: json.loads(o),
        lambda o: json.loads(re.search(
            r'```(?:json)?\s*(\{.*?\})\s*```', o, re.DOTALL).group(1)),
        lambda o: json.loads(re.search(r'(\{.*\})', o, re.DOTALL).group(1)),
    ]
    for fn in strategies:
        try:
            return fn(output)
        except Exception:
            continue
    return None


def discover_service(cfg: Config, svc) -> List[dict]:
    """Run Claude discovery for one service, return list of endpoint dicts."""
    prompt = DISCOVERY_PROMPT.format(
        svc_name=svc.name,
        svc_path=svc.path,
    )

    print(f"   📡 Discovering: {svc.name} ({svc.path})")

    if not os.path.isdir(svc.path):
        print(f"   ⚠️  Path not found: {svc.path} — skipping")
        return []

    result = subprocess.run(
        [cfg.claude_bin, "-p", prompt,
         "--model", cfg.claude_model,
         "--allowedTools", "Read,Glob,Grep"],
        capture_output=True,
        text=True,
        cwd=svc.path,
    )

    output = result.stdout + result.stderr
    data = _parse_claude_json(output)

    if not data:
        print(f"   ⚠️  Could not parse discovery output for {svc.name}")
        print(f"       Raw (first 300 chars): {output[:300]}")
        return []

    endpoints = data.get("endpoints", [])
    
    # Slugify all IDs to ensure valid filenames regardless of what Claude returns
    for ep in endpoints:
        raw_id = ep.get("id", "")
        if not raw_id:
            # Generate ID from service + method + path if missing
            svc  = ep.get("service", "")
            meth = ep.get("method", "")
            path = ep.get("path", "")
            raw_id = f"{svc}_{meth}_{path}"
        ep["id"] = re.sub(r'[^a-zA-Z0-9_-]', '_', raw_id).strip('_')

    lang = data.get("language", "unknown")
    fw   = data.get("framework", "unknown")

    # Ensure service and service_path are set on every endpoint
    for ep in endpoints:
        ep["service"]      = svc.name
        ep["service_path"] = svc.path

    print(f"   ✓  {svc.name}: {len(endpoints)} endpoints ({lang} / {fw})")
    return endpoints


def filter_endpoints(
    all_endpoints: List[dict],
    targets: List[TargetEndpoint],
) -> tuple[List[dict], List[str]]:
    """Filter discovered endpoints to the target whitelist."""
    if not targets:
        return all_endpoints, []

    # Build lookup: normalized_path → target (with optional service filter)
    target_map: Dict[tuple, TargetEndpoint] = {}
    for t in targets:
        key = (_normalize_path(t.path), t.service_name)
        target_map[key] = t

    kept = []
    for ep in all_endpoints:
        norm    = _normalize_path(ep["path"])
        ep_svc  = ep.get("service")
        ep_meth = ep.get("method", "").upper()

        match = (
            target_map.get((norm, ep_svc)) or   # service-specific match
            target_map.get((norm, None))          # any-service match
        )
        if not match:
            continue

        # Method filter
        if match.method.upper() not in ("ANY", ep_meth):
            continue

        ep["acl_priority"] = match.acl_priority
        ep["label"]        = match.label
        kept.append(ep)

    missed = []
    for t in targets:
        norm = _normalize_path(t.path)
        if not any(_normalize_path(ep["path"]) == norm for ep in kept):
            missed.append(t.path)

    return kept, missed


def run(cfg: Config) -> List[dict]:
    """Run discovery for all services and return filtered endpoint list."""
    print()
    all_endpoints = []
    for svc in cfg.services:
        endpoints = discover_service(cfg, svc)
        all_endpoints.extend(endpoints)

    print(f"\n   Total discovered: {len(all_endpoints)} endpoints")

    filtered, missed = filter_endpoints(all_endpoints, cfg.target_endpoints)

    # Save manifest
    manifest_path = os.path.join(
        cfg.manifests_dir, f"{cfg.service}-manifest.json"
    )
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
        for p in missed:
            print(f"   ✗ {p}")
        print()
        print("   All discovered paths:")
        for ep in all_endpoints:
            print(f"   [{ep['service']}] {ep['method']:6} {ep['path']}")

    return filtered