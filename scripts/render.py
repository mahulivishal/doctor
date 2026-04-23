"""
render.py — Phase 3: Render analysis JSON → Markdown docs in parallel.
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional
from config import Config


def _badge(s: str) -> str:
    return {"HIGH": "🔴 HIGH", "MEDIUM": "🟡 MEDIUM", "LOW": "🟢 LOW"}.get(
        s, "⚪ UNKNOWN"
    )


def _safe_list(val) -> list:
    """Always return a list of dicts."""
    if not isinstance(val, list):
        return []
    return [i for i in val if isinstance(i, dict)]


def _safe_str_list(val) -> list:
    """Always return a list of strings."""
    if not isinstance(val, list):
        return []
    return [i for i in val if isinstance(i, str)]


def _table(headers: list, rows: list) -> str:
    if not rows:
        return "_None identified_\n"
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(str(cell)))

    def fmt(r):
        return "| " + " | ".join(
            str(r[i]).ljust(widths[i]) if i < len(r) else "".ljust(widths[i])
            for i in range(len(headers))
        ) + " |"

    sep = "| " + " | ".join("-" * w for w in widths) + " |"
    return fmt(headers) + "\n" + sep + "\n" + "\n".join(fmt(r) for r in rows) + "\n"


def render(data: dict) -> str:
    lines = []
    a = lines.append

    ov = data.get("overview") or {}
    rq = data.get("request") or {}
    rs = data.get("response") or {}
    dm = data.get("data_model") or {}
    fm = data.get("functional_mapping") or {}
    br = data.get("blast_radius") or {}
    im = data.get("implementation_detail") or {}

    method  = data.get("method", "UNKNOWN")
    path    = data.get("path", "")
    service = data.get("service", "")
    api_id  = data.get("api_id", "")

    # ── Header ───────────────────────────────────────────────────────────
    a(f"# `{method}` {path}")
    a(f"**Service:** `{service}`  ")
    a(f"**API ID:** `{api_id}`")
    a("")
    if br.get("severity"):
        a(f"> **Blast Radius:** {_badge(br['severity'])}")
        if br.get("severity_rationale"):
            a(f"> _{br['severity_rationale']}_")
    if ov.get("acl_notes"):
        a(f"\n> ⚠️ **ACL Note:** {ov['acl_notes']}")
    a("")

    # ── Overview ─────────────────────────────────────────────────────────
    a("## Overview")
    if ov.get("summary"):     a(f"**Summary:** {ov['summary']}\n")
    if ov.get("purpose"):     a(f"**Purpose:** {ov['purpose']}\n")
    if ov.get("oms_context"): a(f"**OMS Context:** {ov['oms_context']}\n")

    # ── Request ──────────────────────────────────────────────────────────
    a("## Request")

    headers = _safe_list(rq.get("headers"))
    if headers:
        a("### Headers")
        rows = [[h.get("name",""), h.get("type",""),
                 "✓" if h.get("required") else "",
                 h.get("description",""), h.get("example","")]
                for h in headers]
        a(_table(["Name","Type","Required","Description","Example"], rows))

    path_params = _safe_list(rq.get("path_params"))
    if path_params:
        a("### Path Parameters")
        rows = [[p.get("name",""), p.get("type",""), p.get("description",""),
                 p.get("validation",""), p.get("example","")]
                for p in path_params]
        a(_table(["Name","Type","Description","Validation","Example"], rows))

    query_params = _safe_list(rq.get("query_params"))
    if query_params:
        a("### Query Parameters")
        rows = [[p.get("name",""), p.get("type",""),
                 "✓" if p.get("required") else "",
                 str(p.get("default","")), p.get("description",""), p.get("example","")]
                for p in query_params]
        a(_table(["Name","Type","Required","Default","Description","Example"], rows))

    body = rq.get("body") or {}
    if isinstance(body, dict) and body.get("fields"):
        a("### Request Body")
        a(f"**Content-Type:** `{body.get('content_type','application/json')}`")
        if body.get("description"):
            a(f"\n{body['description']}\n")
        a("")

        def render_fields(fields, depth=0):
            indent = "  " * depth
            for f in _safe_list(fields):
                req = "✓" if f.get("required") else ""
                enum_vals = _safe_str_list(f.get("enum_values"))
                enum_str  = f" Enum: `{'` `'.join(enum_vals)}`" if enum_vals else ""
                valid     = f.get("validation","")
                valid_str = f" Constraints: _{valid}_" if valid else ""
                a(f"{indent}**`{f.get('field','')}`** `{f.get('type','')}` {req}")
                desc = f.get("description","")
                if desc:
                    a(f"{indent}_{desc}_{enum_str}{valid_str}")
                elif enum_str or valid_str:
                    a(f"{indent}{enum_str}{valid_str}")
                if f.get("example") not in (None, "", "string", 0):
                    a(f"{indent}Example: `{f.get('example')}`")
                nested = f.get("nested_fields") or []
                if nested:
                    render_fields(nested, depth + 1)
                a("")

        render_fields(body.get("fields", []))

    elif isinstance(body, dict) and (body.get("schema") or body.get("example")):
        a("### Request Body")
        a(f"**Content-Type:** `{body.get('content_type','application/json')}`\n")
        if body.get("example"):
            a("```json")
            a(json.dumps(body["example"], indent=2))
            a("```")
        a("")

    # ── Response ─────────────────────────────────────────────────────────
    a("## Response")
    for s in _safe_list(rs.get("success")):
        a(f"### {s.get('status_code',200)} — {s.get('description','Success')}")
        resp_headers = _safe_list(s.get("headers"))
        if resp_headers:
            a("**Response Headers:**")
            for h in resp_headers:
                a(f"- `{h.get('name','')}` — {h.get('description','')}")
            a("")
        resp_fields = _safe_list(s.get("fields"))
        if resp_fields:
            rows = [[f.get("field",""), f.get("type",""),
                     f.get("description",""), str(f.get("example",""))]
                    for f in resp_fields]
            a(_table(["Field","Type","Description","Example"], rows))
        elif s.get("example"):
            a("```json")
            a(json.dumps(s["example"], indent=2))
            a("```")
        a("")

    errors = _safe_list(rs.get("errors"))
    if errors:
        a("### Error Responses")
        rows = [[str(e.get("status_code","")), e.get("error_code",""),
                 e.get("description",""), e.get("trigger_condition","")]
                for e in errors]
        a(_table(["Status","Error Code","Description","Trigger Condition"], rows))

    # ── Data Model ───────────────────────────────────────────────────────
    a("## Data Model")
    if dm.get("description"):
        a(f"_{dm['description']}_\n")
    entities = _safe_list(dm.get("entities"))
    if entities:
        for ent in entities:
            ent_type = f" _{ent.get('type','')}_" if ent.get("type") else ""
            a(f"### `{ent.get('name','')}`{ent_type}")
            if ent.get("description"):
                a(f"{ent['description']}\n")
            if ent.get("storage"):
                a(f"**Storage:** `{ent.get('storage','')}` — `{ent.get('location','')}`\n")
            fields = _safe_list(ent.get("fields"))
            if fields:
                rows = []
                for f in fields:
                    enum_vals = _safe_str_list(f.get("enum_values"))
                    enum_str  = ", ".join(f"`{v}`" for v in enum_vals) if enum_vals else ""
                    constraints = f.get("constraints","")
                    combined = " | ".join(filter(None, [constraints, enum_str]))
                    rows.append([
                        f.get("field",""), f.get("type",""),
                        "✓" if not f.get("nullable", True) else "",
                        f.get("description",""), combined
                    ])
                a(_table(["Field","Type","Not Null","Description","Constraints / Enum Values"], rows))
            rels = _safe_str_list(ent.get("relationships"))
            if rels:
                a("**Relationships:** " + ", ".join(f"`{r}`" for r in rels) + "\n")
    else:
        a("_No entity data captured._\n")

    # ── Functional Mapping ───────────────────────────────────────────────
    a("## Functional Mapping  _(Legacy OMS → Modern OMS)_")
    a(f"_{fm.get('description') or 'Field-by-field trace.'}_\n")

    req_fields = _safe_list(fm.get("request_fields"))
    if req_fields:
        a("### Request Fields")
        rows = [[f.get("field",""), f.get("source",""), f.get("destination",""),
                 f.get("transformation","—"), f.get("legacy_equivalent","—"),
                 f.get("modern_equivalent","—"),
                 "✓" if f.get("acl_transform_needed") else ""]
                for f in req_fields]
        if rows:
            a(_table(["Field","Source","Destination","Transform",
                      "Legacy Equiv.","Modern Equiv.","ACL Transform?"], rows))

    resp_fields = _safe_list(fm.get("response_fields"))
    if resp_fields:
        a("### Response Fields")
        rows = [[f.get("field",""), f.get("source",""), f.get("transformation","—"),
                 f.get("legacy_equivalent","—"), f.get("modern_equivalent","—"),
                 "✓" if f.get("acl_transform_needed") else ""]
                for f in resp_fields]
        if rows:
            a(_table(["Field","Source","Transform",
                      "Legacy Equiv.","Modern Equiv.","ACL Transform?"], rows))

    # ── Blast Radius ─────────────────────────────────────────────────────
    a("## Blast Radius")
    a(f"**Severity:** {_badge(br.get('severity',''))}")
    if br.get("severity_rationale"): a(f"\n_{br['severity_rationale']}_\n")
    if br.get("acl_risk"):           a(f"\n> ⚠️ **ACL Risk:** {br['acl_risk']}\n")

    dc = _safe_list(br.get("downstream_consumers"))
    if dc:
        a("### Downstream Consumers")
        rows = [[c.get("service",""), c.get("usage",""), c.get("impact_if_broken","")]
                for c in dc]
        a(_table(["Service","Usage","Impact if Broken"], rows))

    ud = _safe_list(br.get("upstream_dependencies"))
    if ud:
        a("### Upstream Dependencies")
        rows = [[d.get("service_or_resource",""), d.get("dependency_type",""),
                 d.get("failure_mode","")]
                for d in ud]
        a(_table(["Service/Resource","Dependency Type","Failure Mode"], rows))

    mut = br.get("data_mutation") or {}
    if isinstance(mut, dict) and mut.get("mutates_data"):
        a("### Data Mutation")
        a(f"**Mutates data:** Yes  ")
        a(f"**Rollback possible:** {'Yes' if mut.get('rollback_possible') else 'No'}  ")
        locs = _safe_str_list(mut.get("storage_locations_affected"))
        if locs:
            a(f"**Locations affected:** {', '.join(f'`{l}`' for l in locs)}")
        fx = _safe_str_list(mut.get("side_effects"))
        if fx:
            a("\n**Side effects:**")
            for f in fx: a(f"- {f}")
        a("")

    # ── Implementation Detail ─────────────────────────────────────────────
    a("## Implementation Detail")
    a(f"**Handler:** `{im.get('handler_file','')}` → `{im.get('handler_function','')}`  ")
    a(f"**Auth:** `{im.get('auth_mechanism','None')}`  ")
    mc = _safe_str_list(im.get("middleware_chain"))
    if mc:
        a("**Middleware:** " + " → ".join(f"`{m}`" for m in mc))
    a("")

    ec = _safe_list(im.get("external_calls"))
    if ec:
        a("### External Calls")
        rows = [[c.get("target",""), c.get("protocol",""), c.get("operation",""),
                 str(c.get("timeout_ms","—")), c.get("retry_policy","—")]
                for c in ec]
        a(_table(["Target","Protocol","Operation","Timeout (ms)","Retry Policy"], rows))

    cache = im.get("caching") or {}
    if isinstance(cache, dict) and cache.get("enabled"):
        a("### Caching")
        a(f"**Strategy:** `{cache.get('strategy','')}` | "
          f"**TTL:** `{cache.get('ttl_seconds','')}s` | "
          f"**Key:** `{cache.get('cache_key_pattern','')}`\n")

    if im.get("validation_logic"):
        a(f"### Validation\n{im['validation_logic']}\n")
    if im.get("notable_logic"):
        a(f"### Notable Logic\n{im['notable_logic']}\n")

    ambig = _safe_str_list(im.get("ambiguity_notes"))
    if ambig:
        a("### ⚠️ Ambiguities (Needs Manual Review)")
        for note in ambig: a(f"- {note}")
        a("")

    return "\n".join(lines)


def render_file(args) -> tuple:
    """Render one file. Returns (api_id, error_or_None)."""
    fname, analysis_dir, docs_dir, target_id = args
    api_id = fname.replace(".json", "")
    if target_id and api_id != target_id:
        return None, None
    try:
        with open(os.path.join(analysis_dir, fname)) as f:
            data = json.load(f)
        md = render(data)
        out_path = os.path.join(docs_dir, f"{api_id}.md")
        with open(out_path, "w") as f:
            f.write(md)
        return api_id, None
    except Exception as e:
        return api_id, str(e)


def run(cfg: Config, target_id: str = "") -> dict:
    """Render all analysis files to Markdown in parallel."""
    analysis_files = sorted([
        f for f in os.listdir(cfg.analysis_dir) if f.endswith(".json")
    ])

    args_list = [
        (fname, cfg.analysis_dir, cfg.docs_dir, target_id)
        for fname in analysis_files
    ]

    done = errors = 0
    with ThreadPoolExecutor(max_workers=cfg.parallel_workers) as executor:
        for api_id, err in executor.map(render_file, args_list):
            if api_id is None:
                continue
            if err:
                print(f"   ❌ {api_id}: {err}")
                errors += 1
            else:
                print(f"   ✓  {api_id}.md")
                done += 1

    return {"done": done, "errors": errors}