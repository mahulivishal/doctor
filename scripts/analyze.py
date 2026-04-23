"""
analyze.py — Phase 2: Deep-analyze each endpoint in parallel.
One subprocess per endpoint, validated before saving.
"""
import json
import os
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional
from config import Config

REQUIRED_KEYS = [
    "api_id", "service", "method", "path",
    "overview", "request", "response",
    "blast_radius", "implementation_detail",
]

ANALYSIS_PROMPT_TEMPLATE = """\
You are a senior API documentation engineer producing documentation for an ACL migration layer.
Analyze ONE endpoint in the '{svc_name}' service with extreme thoroughness.

TARGET ENDPOINT
Service:          {svc_name}
Method:           {method}
Path:             {ep_path}
Handler File:     {handler}
Handler Function: {handler_fn}
Auth Required:    {auth}

READING STRATEGY — follow this order:
1. Read the handler file: {handler}
2. Find the request body class/model — read it fully including ALL nested classes.
   Java/Kotlin: find the @RequestBody parameter type, read that class and every class it references
   Python:      find the Pydantic model, read it and every nested model
   Go:          find the bound struct, read it and every embedded/referenced struct
3. Find the response type — read it fully
4. Find all validators, services, repositories this endpoint calls
5. Find all external calls (HTTP, Pub/Sub, Kafka, Redis, DB)

DOCUMENTATION PRIORITIES — focus on these in order of importance:
1. What the API does (clear, precise description)
2. Full request schema — EVERY field documented, nested objects fully expanded
3. Full response schema — EVERY field documented
4. Data model — the DOMAIN entities (request/response DTOs and their fields), NOT infrastructure
5. Upstream and downstream dependencies
6. Deep implementation details (validation, auth, caching, external calls, notable logic)
7. Blast radius
8. Ambiguities

CRITICAL RULES
- Return ONLY raw JSON. No markdown. No explanation. No code fences.
- Never infer. Only document what the source code proves.
- For request body: YOU MUST document every field. If the body has nested objects,
  expand each nested object as a separate entry in body.fields array.
  NEVER leave body.fields empty or null for POST/PUT/PATCH endpoints.
- For data_model: document the REQUEST/RESPONSE domain objects (DTOs, data classes),
  NOT Redis caches or infrastructure. Infrastructure goes in implementation_detail.
- For functional_mapping: only populate if there is a real legacy→modern field mapping.
  If the API is greenfield with no legacy mapping, set request_fields and response_fields to [].
- ALL 9 top-level keys are required.

{{
  "api_id": "{api_id}",
  "service": "{svc_name}",
  "method": "{method}",
  "path": "{ep_path}",

  "overview": {{
    "summary": "one precise sentence describing what this endpoint does",
    "purpose": "2-3 sentences: business context, who calls this, what happens as a result",
    "oms_context": "how this fits into OMS order management — be specific",
    "acl_notes": "specific ACL wrapping concerns: enum values to preserve, header handling, idempotency keys, response shape"
  }},

  "request": {{
    "headers": [
      {{"name":"","type":"string","required":false,"description":"purpose and fallback logic","example":""}}
    ],
    "path_params": [
      {{"name":"","type":"","required":true,"description":"","validation":"regex or constraint","example":""}}
    ],
    "query_params": [
      {{"name":"","type":"","required":false,"description":"","default":null,"example":""}}
    ],
    "body": {{
      "content_type": "application/json",
      "description": "one sentence describing the overall request object",
      "fields": [
        {{
          "field": "topLevelField",
          "type": "string|int|boolean|object|array",
          "required": true,
          "description": "what this field means and how it is used",
          "validation": "any @NotNull @Length @Pattern constraints from source",
          "example": "concrete example value",
          "nested_fields": [
            {{
              "field": "nestedField",
              "type": "string",
              "required": false,
              "description": "",
              "validation": "",
              "example": ""
            }}
          ]
        }}
      ]
    }}
  }},

  "response": {{
    "success": [
      {{
        "status_code": 200,
        "description": "what is returned and why this status code",
        "headers": [{{"name":"","description":""}}],
        "fields": [
          {{
            "field": "",
            "type": "",
            "description": "",
            "example": ""
          }}
        ]
      }}
    ],
    "errors": [
      {{
        "status_code": 400,
        "error_code": "",
        "description": "",
        "trigger_condition": "exactly what in the code causes this — be specific"
      }}
    ]
  }},

  "data_model": {{
    "description": "The domain objects this endpoint operates on",
    "entities": [
      {{
        "name": "RequestBodyClassName",
        "type": "request_dto|response_dto|domain_entity|event",
        "description": "what this object represents in business terms",
        "fields": [
          {{
            "field": "",
            "type": "",
            "nullable": true,
            "description": "business meaning of this field",
            "constraints": "validation rules from source code",
            "enum_values": []
          }}
        ],
        "relationships": ["references OrderLine", "extends BaseOrder"]
      }}
    ]
  }},

  "functional_mapping": {{
    "description": "Legacy OMS → Modern OMS field mapping. Set arrays to [] if no legacy mapping exists.",
    "request_fields": [
      {{
        "field": "",
        "source": "request body|path param|query param|header",
        "destination": "where this field goes — DB column, event field, downstream service",
        "transformation": "any transform: enum remap, type cast, hash, UUID generation",
        "legacy_equivalent": null,
        "modern_equivalent": null,
        "acl_transform_needed": false,
        "notes": ""
      }}
    ],
    "response_fields": [
      {{
        "field": "",
        "source": "computed|DB|event|upstream service",
        "transformation": "",
        "legacy_equivalent": null,
        "modern_equivalent": null,
        "acl_transform_needed": false,
        "notes": ""
      }}
    ]
  }},

  "blast_radius": {{
    "severity": "HIGH|MEDIUM|LOW",
    "severity_rationale": "one sentence: why this severity — what breaks if this endpoint fails",
    "downstream_consumers": [
      {{
        "service": "",
        "usage": "how they consume this endpoint or its side effects",
        "impact_if_broken": "specific impact — not generic"
      }}
    ],
    "upstream_dependencies": [
      {{
        "service_or_resource": "",
        "dependency_type": "synchronous HTTP|Redis|PostgreSQL|Pub/Sub|Kafka|gRPC",
        "failure_mode": "exactly what happens to this endpoint if the dependency fails"
      }}
    ],
    "data_mutation": {{
      "mutates_data": false,
      "storage_locations_affected": [],
      "rollback_possible": false,
      "side_effects": ["list every side effect: events published, caches written, emails sent"]
    }},
    "acl_risk": "specific risks the ACL layer introduces for this endpoint"
  }},

  "implementation_detail": {{
    "handler_file": "{handler}",
    "handler_function": "{handler_fn}",
    "middleware_chain": ["list in order of execution"],
    "auth_mechanism": "exact mechanism from source code",
    "rate_limiting": null,
    "caching": {{
      "enabled": false,
      "strategy": "describe the caching approach if any",
      "ttl_seconds": null,
      "cache_key_pattern": "exact pattern from source"
    }},
    "external_calls": [
      {{
        "target": "",
        "protocol": "HTTP|Redis|SQL|gRPC|Pub/Sub|Kafka",
        "operation": "what exactly is done — publish, get, set, query",
        "timeout_ms": null,
        "retry_policy": null
      }}
    ],
    "validation_logic": "describe ALL validation — bean validation annotations, custom validators, order of execution",
    "notable_logic": "non-obvious business logic, gotchas, edge cases — be specific",
    "ambiguity_notes": [
      "list anything that cannot be verified from source — shared libs, external config, inferred behaviour"
    ]
  }}
}}\
"""


def _parse_output(output: str) -> Optional[dict]:
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


def _validate(data: dict) -> List[str]:
    """Return list of missing required keys."""
    return [k for k in REQUIRED_KEYS if k not in data]


def _is_valid_cached(path: str) -> bool:
    """Check if a cached analysis file is valid."""
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        return False
    try:
        with open(path) as f:
            data = json.load(f)
        return len(_validate(data)) == 0
    except Exception:
        return False


def analyze_endpoint(cfg: Config, ep: dict, max_retries: int = 3) -> bool:
    """
    Analyze one endpoint. Returns True on success, False on failure.
    All I/O uses temp files — no shell quoting, safe for any path/value.
    """
    api_id     = ep.get("id", "")
    method     = ep.get("method", "")
    ep_path    = ep.get("path", "")
    handler    = ep.get("handler_file", "unknown")
    handler_fn = ep.get("handler_function", "unknown")
    auth       = str(ep.get("auth_required", False))
    svc_name   = ep.get("service", cfg.service)
    svc_path   = ep.get("service_path", cfg.repo_root)

    output_file = os.path.join(cfg.analysis_dir, f"{api_id}.json")

    # Skip if cached and valid
    if _is_valid_cached(output_file):
        print(f"   ⏭  [{svc_name}] {method} {ep_path} (cached)")
        return True
    elif os.path.exists(output_file):
        print(f"   ♻️  [{svc_name}] {method} {ep_path} (re-analyzing invalid cache)")
        os.remove(output_file)

    print(f"   🔬 [{svc_name}] {method} {ep_path}")

    prompt = ANALYSIS_PROMPT_TEMPLATE.format(
        api_id=api_id,
        svc_name=svc_name,
        method=method,
        ep_path=ep_path,
        handler=handler,
        handler_fn=handler_fn,
        auth=auth,
    )

    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            print(f"      ↻  [{svc_name}] {api_id} retry {attempt}/{max_retries}")

        # Write prompt to temp file — completely bypasses shell quoting
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as pf:
            pf.write(prompt)
            prompt_file = pf.name

        try:
            cmd = [cfg.claude_bin, "-p", prompt,
                   "--allowedTools", "Read,Glob,Grep"]
            if cfg.claude_model:
                cmd.extend(["--model", cfg.claude_model])
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=svc_path,
            )
            output = result.stdout + result.stderr

        finally:
            os.unlink(prompt_file)

        data = _parse_output(output)
        if data is None:
            print(f"      ⚠️  Attempt {attempt}: PARSE_FAILED")
            continue

        missing = _validate(data)
        if missing:
            print(f"      ⚠️  Attempt {attempt}: VALIDATION_FAILED missing={missing}")
            continue

        # Valid — save
        os.makedirs(cfg.analysis_dir, exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)
        print(f"      ✓  [{svc_name}] {api_id}")
        return True

    print(f"      ❌ [{svc_name}] {api_id} failed after {max_retries} attempts")
    return False


def run(cfg: Config, endpoints: List[dict], target_id: str = "") -> dict:
    """Run parallel analysis. Returns {done, failed, skipped} counts."""
    if target_id:
        endpoints = [ep for ep in endpoints if ep.get("id") == target_id]
        print(f"🎯 Single-endpoint mode: {target_id}")

    total = len(endpoints)
    print(f"📊 Found {total} endpoints to analyze (~1-5 min each)")
    print(f"   Model: {cfg.claude_model}")
    print(f"   Workers: {cfg.parallel_workers} parallel")
    print()
    print("🚀 Starting analysis...")
    print()

    done = failed = skipped = 0

    with ThreadPoolExecutor(max_workers=cfg.parallel_workers) as executor:
        futures = {
            executor.submit(analyze_endpoint, cfg, ep): ep
            for ep in endpoints
        }
        for future in as_completed(futures):
            ep = futures[future]
            try:
                success = future.result()
                if success:
                    # Distinguish cached vs newly analyzed
                    api_id = ep.get("id", "")
                    output_file = os.path.join(cfg.analysis_dir, f"{api_id}.json")
                    # If file existed before we started, it was skipped
                    done += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"      ❌ Unexpected error for {ep.get('id','?')}: {e}")
                failed += 1

    return {"done": done, "failed": failed, "total": total}