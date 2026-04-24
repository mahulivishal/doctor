"""
artifacts.py — Phase 5: Generate Postman collections, Mermaid data model
charts, and ER diagrams from existing analysis JSON files.
Zero additional Claude calls — pure Python generation.
"""
import json
import os
import uuid
from collections import defaultdict
from typing import List, Optional
from config import Config


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _safe_list(val) -> list:
    if not isinstance(val, list): return []
    return [i for i in val if isinstance(i, dict)]

def _safe_str_list(val) -> list:
    if not isinstance(val, list): return []
    return [i for i in val if isinstance(i, str)]

def _load_analyses(cfg: Config) -> List[dict]:
    apis = []
    for fname in sorted(os.listdir(cfg.analysis_dir)):
        if fname.endswith(".json"):
            with open(os.path.join(cfg.analysis_dir, fname)) as f:
                try:
                    apis.append(json.load(f))
                except Exception:
                    pass
    return apis


# ─── 1. Postman Collection ────────────────────────────────────────────────────

def _postman_body(api: dict) -> Optional[dict]:
    """Build Postman raw body from analysis body.fields."""
    body = (api.get("request") or {}).get("body") or {}
    if not isinstance(body, dict):
        return None

    def fields_to_example(fields) -> dict:
        result = {}
        for f in _safe_list(fields):
            name = f.get("field", "")
            if not name:
                continue
            ftype   = f.get("type", "string").lower()
            example = f.get("example")
            nested  = f.get("nested_fields") or []

            if nested:
                result[name] = fields_to_example(nested)
            elif example not in (None, "", "string"):
                result[name] = example
            elif "int" in ftype or "number" in ftype or "float" in ftype:
                result[name] = 0
            elif "bool" in ftype:
                result[name] = False
            elif "array" in ftype or "list" in ftype:
                result[name] = []
            else:
                result[name] = f"<{name}>"
        return result

    if body.get("fields"):
        example = fields_to_example(body["fields"])
        return {
            "mode": "raw",
            "raw": json.dumps(example, indent=2),
            "options": {"raw": {"language": "json"}}
        }
    return None


def _postman_headers(api: dict) -> list:
    headers = []
    for h in _safe_list((api.get("request") or {}).get("headers")):
        headers.append({
            "key":   h.get("name", ""),
            "value": h.get("example", ""),
            "description": h.get("description", ""),
        })
    # Always add Content-Type for bodies
    method = api.get("method", "")
    if method in ("POST", "PUT", "PATCH"):
        if not any(h["key"].lower() == "content-type" for h in headers):
            headers.append({
                "key": "Content-Type",
                "value": "application/json",
                "description": "Request body content type",
            })
    return headers


def _postman_url(api: dict, base_url: str) -> dict:
    path = api.get("path", "")
    # Convert {param} and {param:.+} to :param for Postman
    import re
    postman_path = re.sub(r'\{([^}:]+)(?::[^}]*)?\}', r':\1', path)
    segments = [s for s in postman_path.split("/") if s]

    query = []
    for qp in _safe_list((api.get("request") or {}).get("query_params")):
        query.append({
            "key":   qp.get("name", ""),
            "value": str(qp.get("example", "")),
            "description": qp.get("description", ""),
            "disabled": not qp.get("required", False),
        })

    return {
        "raw":      f"{base_url}/{'/'.join(segments)}",
        "protocol": "https",
        "host":     ["{{base_url}}"],
        "path":     segments,
        "query":    query,
        "variable": [
            {"key": re.sub(r'^:', '', s), "value": "", "description": ""}
            for s in segments if s.startswith(":")
        ],
    }


def _build_postman_item(api: dict, base_url: str) -> dict:
    method  = api.get("method", "GET")
    path    = api.get("path", "")
    summary = (api.get("overview") or {}).get("summary", path)
    label   = api.get("label", "")
    name    = label if label else f"{method} {path}"

    item = {
        "name": name,
        "request": {
            "method":      method,
            "header":      _postman_headers(api),
            "url":         _postman_url(api, base_url),
            "description": summary,
        },
        "response": [],
    }

    body = _postman_body(api)
    if body:
        item["request"]["body"] = body

    # Add example success response
    for s in _safe_list((api.get("response") or {}).get("success")):
        resp_fields = _safe_list(s.get("fields"))
        if resp_fields:
            example_body = {f.get("field",""): f.get("example","") for f in resp_fields}
        else:
            example_body = s.get("example") or {}
        item["response"].append({
            "name":            f"{s.get('status_code',200)} Example",
            "originalRequest": item["request"],
            "status":          "OK" if s.get("status_code",200) == 200 else "Accepted",
            "code":            s.get("status_code", 200),
            "header":          [{"key":"Content-Type","value":"application/json"}],
            "body":            json.dumps(example_body, indent=2),
        })

    return item


def generate_postman(cfg: Config, apis: List[dict]) -> None:
    """Generate one Postman collection per service."""
    postman_dir = os.path.join(cfg.output_dir, "postman")
    os.makedirs(postman_dir, exist_ok=True)

    # Group by service
    by_service = defaultdict(list)
    for api in apis:
        by_service[api.get("service", cfg.service)].append(api)

    for service, service_apis in by_service.items():
        # Group by first path segment as folder
        folders = defaultdict(list)
        for api in service_apis:
            path = api.get("path", "/")
            segment = path.strip("/").split("/")[0] if "/" in path.strip("/") else "root"
            folders[segment].append(_build_postman_item(api, "{{base_url}}"))

        items = []
        for folder_name, folder_items in sorted(folders.items()):
            items.append({
                "name":  folder_name,
                "item":  folder_items,
            })

        collection = {
            "info": {
                "_postman_id": str(uuid.uuid4()),
                "name":        f"Doctor — {service}",
                "description": f"Auto-generated by Doctor (api-doc-forge). Service: {service}",
                "schema":      "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "variable": [
                {"key": "base_url", "value": "https://your-service-host", "type": "string"}
            ],
            "item": items,
        }

        out_path = os.path.join(postman_dir, f"{service}.postman_collection.json")
        with open(out_path, "w") as f:
            json.dump(collection, f, indent=2)
        print(f"   ✓  postman/{service}.postman_collection.json")


# ─── 2. Mermaid Data Model Diagram ───────────────────────────────────────────

def _mermaid_data_model(api: dict) -> str:
    """Generate a Mermaid classDiagram for the API's domain entities."""
    dm       = api.get("data_model") or {}
    entities = _safe_list(dm.get("entities"))
    if not entities:
        return ""

    lines = ["```mermaid", "classDiagram"]

    for ent in entities:
        name   = ent.get("name", "").replace(" ", "_").replace("-", "_")
        etype  = ent.get("type", "")
        fields = _safe_list(ent.get("fields"))

        lines.append(f"  class {name} {{")
        if etype:
            lines.append(f"    <<{etype}>>")
        for f in fields:
            fname     = f.get("field", "")
            ftype     = f.get("type", "String").replace(" ", "").replace("|", "_or_")
            nullable  = "?" if f.get("nullable", True) else ""
            enum_vals = _safe_str_list(f.get("enum_values"))
            enum_str  = f" // {', '.join(enum_vals)}" if enum_vals else ""
            lines.append(f"    {ftype}{nullable} {fname}{enum_str}")
        lines.append("  }")

    # Relationships
    for ent in entities:
        name = ent.get("name", "").replace(" ", "_").replace("-", "_")
        for rel in _safe_str_list(ent.get("relationships")):
            # Parse common patterns: "X hasMany Y", "X extends Y", "X references Y"
            import re
            m = re.match(
                r'(\w+)?\s*(hasMany|hasOne|extends|references|contains|uses|belongsTo)\s+(\w+)',
                rel, re.IGNORECASE
            )
            if m:
                left  = m.group(1) or name
                rtype = m.group(2).lower()
                right = m.group(3)
                arrow_map = {
                    "hasmany":    f"  {left} \"1\" --> \"*\" {right}",
                    "hasonone":   f"  {left} \"1\" --> \"1\" {right}",
                    "extends":    f"  {right} <|-- {left}",
                    "references": f"  {left} --> {right}",
                    "contains":   f"  {left} *-- {right}",
                    "uses":       f"  {left} ..> {right}",
                    "belongsto":  f"  {left} --> {right}",
                }
                arrow = arrow_map.get(rtype, f"  {left} --> {right}")
                lines.append(arrow)

    lines.append("```")
    return "\n".join(lines)


# ─── 3. ER Diagram ───────────────────────────────────────────────────────────

def _mermaid_er_diagram(apis: List[dict]) -> str:
    """Generate a Mermaid erDiagram across all APIs for a service."""
    lines = ["```mermaid", "erDiagram"]

    seen_entities = set()

    for api in apis:
        dm       = api.get("data_model") or {}
        entities = _safe_list(dm.get("entities"))

        for ent in entities:
            name = ent.get("name", "").replace(" ", "_").replace("-", "_")
            if name in seen_entities:
                continue
            seen_entities.add(name)

            fields = _safe_list(ent.get("fields"))
            lines.append(f"  {name} {{")
            for f in fields:
                fname    = f.get("field", "").replace("-", "_")
                ftype    = (f.get("type") or "String").split("|")[0].split("<")[0].strip()
                ftype    = ftype.replace(" ", "_") or "String"
                nullable = "nullable" if f.get("nullable", True) else "not_null"
                enum_vals = _safe_str_list(f.get("enum_values"))
                comment  = f'"{", ".join(enum_vals[:3])}"' if enum_vals else f'"{f.get("description","")[:40]}"' if f.get("description") else '""'
                lines.append(f"    {ftype} {fname} {nullable} {comment}")
            lines.append("  }")

        # ER relationships from data model
        for ent in entities:
            name = ent.get("name", "").replace(" ", "_").replace("-", "_")
            for rel in _safe_str_list(ent.get("relationships")):
                import re
                m = re.match(
                    r'(\w+)?\s*(hasMany|hasOne|extends|references|contains|belongsTo)\s+(\w+)',
                    rel, re.IGNORECASE
                )
                if m:
                    left  = m.group(1) or name
                    rtype = m.group(2).lower()
                    right = m.group(3)
                    er_map = {
                        "hasmany":    f"  {left} ||--o{{ {right} : has",
                        "hasonone":   f"  {left} ||--|| {right} : has",
                        "extends":    f"  {left} ||--|| {right} : extends",
                        "references": f"  {left} }}o--|| {right} : references",
                        "contains":   f"  {left} ||--|{{ {right} : contains",
                        "belongsto":  f"  {left} }}o--|| {right} : belongs_to",
                    }
                    arrow = er_map.get(rtype, f"  {left} }}o--o{{ {right} : relates")
                    lines.append(arrow)

    lines.append("```")
    return "\n".join(lines)


def generate_diagrams(cfg: Config, apis: List[dict]) -> None:
    """Generate per-API Mermaid diagrams and a combined ER diagram per service."""
    diagrams_dir = os.path.join(cfg.output_dir, "diagrams")
    os.makedirs(diagrams_dir, exist_ok=True)

    # Per-API data model diagrams
    for api in apis:
        api_id  = api.get("api_id", "unknown")
        diagram = _mermaid_data_model(api)
        if not diagram:
            continue
        method  = api.get("method", "")
        path    = api.get("path", "")
        summary = (api.get("overview") or {}).get("summary", "")

        content = f"# Data Model — `{method}` {path}\n\n"
        if summary:
            content += f"_{summary}_\n\n"
        content += "## Class Diagram\n\n"
        content += diagram + "\n"

        out_path = os.path.join(diagrams_dir, f"{api_id}_datamodel.md")
        with open(out_path, "w") as f:
            f.write(content)
        print(f"   ✓  diagrams/{api_id}_datamodel.md")

    # Combined ER diagram per service
    by_service = defaultdict(list)
    for api in apis:
        by_service[api.get("service", cfg.service)].append(api)

    for service, service_apis in by_service.items():
        er = _mermaid_er_diagram(service_apis)
        content = f"# ER Diagram — {service}\n\n"
        content += "_Entity relationships across all documented APIs_\n\n"
        content += er + "\n"

        out_path = os.path.join(diagrams_dir, f"{service}_er_diagram.md")
        with open(out_path, "w") as f:
            f.write(content)
        print(f"   ✓  diagrams/{service}_er_diagram.md")


# ─── Embed diagrams into existing API docs ────────────────────────────────────

def embed_diagrams_in_docs(cfg: Config, apis: List[dict]) -> None:
    """Append Mermaid data model diagram to each existing API markdown doc."""
    for api in apis:
        api_id  = api.get("api_id", "")
        doc_path = os.path.join(cfg.docs_dir, f"{api_id}.md")
        if not os.path.exists(doc_path):
            continue

        diagram = _mermaid_data_model(api)
        if not diagram:
            continue

        with open(doc_path) as f:
            existing = f.read()

        # Don't embed twice
        if "classDiagram" in existing:
            continue

        with open(doc_path, "a") as f:
            f.write("\n## Data Model Diagram\n\n")
            f.write(diagram)
            f.write("\n")

    print(f"   ✓  Mermaid diagrams embedded in output/docs/")


# ─── Phase entry point ────────────────────────────────────────────────────────

def run(cfg: Config) -> None:
    print()
    apis = _load_analyses(cfg)

    if not apis:
        print("   ⚠️  No analysis files found — run Phase 2 first")
        return

    print(f"   Generating artifacts for {len(apis)} APIs...\n")

    print("📮 Postman Collections")
    generate_postman(cfg, apis)

    print("\n📊 Mermaid Diagrams")
    generate_diagrams(cfg, apis)

    print("\n🔗 Embedding diagrams in API docs")
    embed_diagrams_in_docs(cfg, apis)

    print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Artifacts complete!
   output/
   ├── postman/
   │   └── <service>.postman_collection.json
   └── diagrams/
       ├── <api_id>_datamodel.md   (per API)
       └── <service>_er_diagram.md (per service)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")