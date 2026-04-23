"""
assemble.py — Phase 4: Build master README, ACL checklist, api-registry.json.
"""
import json
import os
import datetime
from typing import List
from config import Config


def _badge(s: str) -> str:
    return {"HIGH": "🔴 HIGH", "MEDIUM": "🟡 MEDIUM", "LOW": "🟢 LOW"}.get(
        s, "⚪ UNKNOWN"
    )


def _safe_list(val) -> list:
    if not isinstance(val, list): return []
    return [i for i in val if isinstance(i, dict)]


def _safe_str_list(val) -> list:
    if not isinstance(val, list): return []
    return [i for i in val if isinstance(i, str)]


def _acl_transform_count(api: dict) -> int:
    fm = api.get("functional_mapping") or {}
    return sum(
        1 for f in
        _safe_list(fm.get("request_fields")) + _safe_list(fm.get("response_fields"))
        if f.get("acl_transform_needed")
    )


def _complexity(api: dict) -> str:
    transforms = _acl_transform_count(api)
    ext_calls  = len(_safe_list(
        (api.get("implementation_detail") or {}).get("external_calls")
    ))
    severity   = (api.get("blast_radius") or {}).get("severity", "LOW")
    score = transforms + ext_calls * 2 + {"HIGH": 5, "MEDIUM": 2, "LOW": 0}.get(severity, 0)
    if score >= 8: return "Complex"
    if score >= 3: return "Moderate"
    return "Simple"


def run(cfg: Config) -> None:
    # ── Load analysis files ───────────────────────────────────────────────
    apis = []
    for fname in sorted(os.listdir(cfg.analysis_dir)):
        if fname.endswith(".json"):
            with open(os.path.join(cfg.analysis_dir, fname)) as f:
                apis.append(json.load(f))

    total = len(apis)
    now   = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

    apis_sorted = sorted(
        apis,
        key=lambda a: (
            SEVERITY_ORDER.get((a.get("blast_radius") or {}).get("severity", "LOW"), 99),
            a.get("path", "")
        )
    )

    high   = [x for x in apis_sorted if (x.get("blast_radius") or {}).get("severity") == "HIGH"]
    medium = [x for x in apis_sorted if (x.get("blast_radius") or {}).get("severity") == "MEDIUM"]
    low    = [x for x in apis_sorted if (x.get("blast_radius") or {}).get("severity") == "LOW"]

    service_name = apis[0].get("service", cfg.service) if apis else cfg.service

    # ── 1. api-registry.json ─────────────────────────────────────────────
    registry = []
    for api in apis_sorted:
        br = api.get("blast_radius") or {}
        im = api.get("implementation_detail") or {}
        registry.append({
            "api_id":         api.get("api_id"),
            "service":        api.get("service"),
            "method":         api.get("method"),
            "path":           api.get("path"),
            "summary":        (api.get("overview") or {}).get("summary", ""),
            "auth_required":  im.get("auth_mechanism", "None") != "None",
            "blast_severity": br.get("severity", "UNKNOWN"),
            "acl_transforms": _acl_transform_count(api),
            "complexity":     _complexity(api),
            "doc_file":       f"docs/{api.get('api_id')}.md",
        })

    registry_path = os.path.join(cfg.output_dir, "api-registry.json")
    with open(registry_path, "w") as f:
        json.dump(registry, f, indent=2)
    print(f"✓  api-registry.json ({len(registry)} entries)")

    # ── 2. README.md ─────────────────────────────────────────────────────
    lines = []
    a = lines.append

    a(f"# API Documentation — {service_name}")
    a(f"_Generated: {now}_\n")
    a(f"**Total APIs:** {total}  ")
    a(f"**Blast Radius:** 🔴 HIGH: {len(high)} &nbsp;|&nbsp; "
      f"🟡 MEDIUM: {len(medium)} &nbsp;|&nbsp; 🟢 LOW: {len(low)}\n")
    a("---\n")

    a("## All Endpoints\n")
    a("| Method | Path | Summary | Blast Radius | ACL Transforms | Complexity | Doc |")
    a("|--------|------|---------|--------------|----------------|------------|-----|")
    for api in apis_sorted:
        br         = api.get("blast_radius") or {}
        sev        = _badge(br.get("severity", ""))
        transforms = _acl_transform_count(api)
        comp       = _complexity(api)
        doc_link   = f"[📄](docs/{api.get('api_id')}.md)"
        summary    = ((api.get("overview") or {}).get("summary") or "")[:60]
        a(f"| `{api.get('method','')}` | `{api.get('path','')}` | {summary} "
          f"| {sev} | {transforms} | {comp} | {doc_link} |")

    a("\n---\n")

    if high:
        a("## 🔴 High Blast Radius APIs\n")
        a("> These APIs must be wrapped and tested first in the ACL layer.\n")
        for api in high:
            br = api.get("blast_radius") or {}
            a(f"### `{api.get('method','')}` {api.get('path','')}")
            a(f"_{(api.get('overview') or {}).get('summary', '')}_\n")
            a(f"**Rationale:** {br.get('severity_rationale', '')}")
            a(f"**ACL Risk:** {br.get('acl_risk', '_Not specified_')}")
            dc = _safe_list(br.get("downstream_consumers"))
            if dc:
                a("\n**Downstream consumers:** " +
                  ", ".join(f"`{c.get('service','')}`" for c in dc))
            fx = _safe_str_list((br.get("data_mutation") or {}).get("side_effects"))
            if fx:
                a("\n**Side effects:**")
                for f in fx: a(f"- {f}")
            a(f"\n→ [Full doc](docs/{api.get('api_id')}.md)\n")

    a("---\n")
    a("## Functional Mapping Cross-Reference\n")
    a("Fields that require ACL transformation, grouped by transform type.\n")

    transform_map: dict = {}
    for api in apis:
        fm = api.get("functional_mapping") or {}
        for fld in (_safe_list(fm.get("request_fields")) +
                    _safe_list(fm.get("response_fields"))):
            if fld.get("acl_transform_needed") and fld.get("transformation"):
                t = fld["transformation"]
                transform_map.setdefault(t, []).append({
                    "api_id": api.get("api_id"),
                    "field":  fld.get("field", "—"),
                    "legacy": fld.get("legacy_equivalent", "—"),
                    "modern": fld.get("modern_equivalent", "—"),
                })

    if transform_map:
        for transform, usages in sorted(transform_map.items()):
            a(f"### `{transform}`")
            a(f"_Used in {len(usages)} field(s) across "
              f"{len(set(u['api_id'] for u in usages))} API(s)_\n")
            a("| API | Field | Legacy | Modern |")
            a("|-----|-------|--------|--------|")
            for u in usages:
                a(f"| `{u['api_id']}` | `{u['field']}` "
                  f"| `{u['legacy']}` | `{u['modern']}` |")
            a("")
    else:
        a("_No ACL transforms identified._\n")

    with open(os.path.join(cfg.output_dir, "README.md"), "w") as f:
        f.write("\n".join(lines))
    print("✓  README.md (master index)")

    # ── 3. ACL-CHECKLIST.md ───────────────────────────────────────────────
    lines = []
    a = lines.append

    a(f"# ACL Implementation Checklist — {service_name}")
    a(f"_Generated: {now}_\n")
    a("> Work through in order: HIGH first, then MEDIUM, then LOW.\n")
    a("---\n")
    a("## Implementation Order\n")

    for label, group in [
        ("🔴 HIGH — Implement First", high),
        ("🟡 MEDIUM", medium),
        ("🟢 LOW — Implement Last", low),
    ]:
        if not group: continue
        a(f"### {label}\n")
        for api in group:
            br         = api.get("blast_radius") or {}
            im         = api.get("implementation_detail") or {}
            transforms = _acl_transform_count(api)
            comp       = _complexity(api)
            a(f"- [ ] **`{api.get('method','')}` `{api.get('path','')}`** "
              f"&nbsp; _{comp} complexity, {transforms} field transform(s)_")
            if br.get("acl_risk"):
                a(f"  - ⚠️ {br['acl_risk']}")
            ext_calls = _safe_list(im.get("external_calls"))
            if ext_calls:
                targets = [c.get("target","") for c in ext_calls if c.get("target")]
                if targets:
                    a(f"  - External calls: {', '.join(f'`{t}`' for t in targets)}")
        a("")

    a("---\n")
    a("## ACL Transform Catalogue\n")

    all_transforms = set()
    for api in apis:
        fm = api.get("functional_mapping") or {}
        for fld in (_safe_list(fm.get("request_fields")) +
                    _safe_list(fm.get("response_fields"))):
            if fld.get("acl_transform_needed") and fld.get("transformation"):
                all_transforms.add(fld["transformation"])

    if all_transforms:
        for t in sorted(all_transforms):
            a(f"- [ ] `{t}`")
    else:
        a("_No transforms identified._")

    a("\n---\n")
    a("## Ambiguities Requiring Manual Review\n")

    found_ambig = False
    for api in apis:
        im    = api.get("implementation_detail") or {}
        notes = _safe_str_list(im.get("ambiguity_notes"))
        if notes:
            found_ambig = True
            a(f"### `{api.get('method','')}` `{api.get('path','')}`")
            for note in notes: a(f"- ⚠️ {note}")
            a("")

    if not found_ambig:
        a("_No ambiguities flagged._\n")

    with open(os.path.join(cfg.output_dir, "ACL-CHECKLIST.md"), "w") as f:
        f.write("\n".join(lines))
    print("✓  ACL-CHECKLIST.md")

    print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Assembly complete!
   output/
   ├── README.md
   ├── ACL-CHECKLIST.md
   ├── api-registry.json
   └── docs/ ({total} files)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
