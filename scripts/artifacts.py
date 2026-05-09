"""
artifacts.py — Phase 5: Generate Postman collections, Mermaid data model
charts, per-service ER diagrams, and Swagger/OpenAPI YAML.
Zero additional Claude calls — pure Python generation.

Output structure:
  output/
  ├── documents/            ← API markdown docs (rendered by render.py)
  ├── data_model/           ← Mermaid classDiagram per API
  ├── db_entity_relations/  ← Mermaid erDiagram per SERVICE
  ├── postman_collection/   ← Postman collection per service
  └── api_document/         ← OpenAPI 3.0 YAML per service
"""
import json
import os
import re
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

def _slugify(s: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_-]', '_', s).strip('_')

def _normalize_path_postman(path: str) -> str:
    """Convert {param} and {param:.+} to :param for Postman."""
    return re.sub(r'\{([^}:]+)(?::[^}]*)?\}', r':\1', path)


# ─── 1. Postman Collection ────────────────────────────────────────────────────

def _postman_body(api: dict) -> Optional[dict]:
    body = (api.get("request") or {}).get("body") or {}
    if not isinstance(body, dict) or not body.get("fields"):
        return None

    def fields_to_example(fields) -> dict:
        result = {}
        for f in _safe_list(fields):
            name    = f.get("field", "")
            ftype   = f.get("type", "string").lower()
            example = f.get("example")
            nested  = f.get("nested_fields") or []
            if not name:
                continue
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

    example = fields_to_example(body["fields"])
    return {
        "mode": "raw",
        "raw": json.dumps(example, indent=2),
        "options": {"raw": {"language": "json"}},
    }


def _postman_headers(api: dict) -> list:
    headers = []
    for h in _safe_list((api.get("request") or {}).get("headers")):
        headers.append({
            "key":         h.get("name", ""),
            "value":       h.get("example", ""),
            "description": h.get("description", ""),
        })
    if api.get("method", "") in ("POST", "PUT", "PATCH"):
        if not any(h["key"].lower() == "content-type" for h in headers):
            headers.append({
                "key":         "Content-Type",
                "value":       "application/json",
                "description": "Request body content type",
            })
    return headers


def _postman_url(api: dict) -> dict:
    postman_path = _normalize_path_postman(api.get("path", ""))
    segments     = [s for s in postman_path.split("/") if s]
    query = [
        {
            "key":      qp.get("name", ""),
            "value":    str(qp.get("example", "")),
            "description": qp.get("description", ""),
            "disabled": not qp.get("required", False),
        }
        for qp in _safe_list((api.get("request") or {}).get("query_params"))
    ]
    return {
        "raw":      "{{base_url}}/" + "/".join(segments),
        "protocol": "https",
        "host":     ["{{base_url}}"],
        "path":     segments,
        "query":    query,
        "variable": [
            {"key": s.lstrip(":"), "value": "", "description": ""}
            for s in segments if s.startswith(":")
        ],
    }


def _build_postman_item(api: dict) -> dict:
    method  = api.get("method", "GET")
    path    = api.get("path", "")
    summary = (api.get("overview") or {}).get("summary", path)
    name    = api.get("label") or f"{method} {path}"

    item = {
        "name": name,
        "request": {
            "method":      method,
            "header":      _postman_headers(api),
            "url":         _postman_url(api),
            "description": summary,
        },
        "response": [],
    }

    body = _postman_body(api)
    if body:
        item["request"]["body"] = body

    for s in _safe_list((api.get("response") or {}).get("success")):
        resp_fields  = _safe_list(s.get("fields"))
        example_body = {f.get("field", ""): f.get("example", "") for f in resp_fields} \
                       if resp_fields else (s.get("example") or {})
        item["response"].append({
            "name":            f"{s.get('status_code', 200)} Example",
            "originalRequest": item["request"],
            "status":          "OK",
            "code":            s.get("status_code", 200),
            "header":          [{"key": "Content-Type", "value": "application/json"}],
            "body":            json.dumps(example_body, indent=2),
        })

    return item


def generate_postman(cfg: Config, apis: List[dict]) -> None:
    """One Postman collection per service → postman_collection/"""
    by_service = defaultdict(list)
    for api in apis:
        by_service[api.get("service", cfg.service)].append(api)

    for service, service_apis in by_service.items():
        folders = defaultdict(list)
        for api in service_apis:
            segment = api.get("path", "/").strip("/").split("/")[0] or "root"
            folders[segment].append(_build_postman_item(api))

        collection = {
            "info": {
                "_postman_id": str(uuid.uuid4()),
                "name":        f"Doctor — {service}",
                "description": f"Auto-generated by Doctor. Service: {service}",
                "schema":      "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "variable": [
                {"key": "base_url", "value": "https://your-service-host", "type": "string"}
            ],
            "item": [
                {"name": folder, "item": items}
                for folder, items in sorted(folders.items())
            ],
        }

        out_path = os.path.join(cfg.postman_dir, f"{service}.postman_collection.json")
        with open(out_path, "w") as f:
            json.dump(collection, f, indent=2)
        print(f"   ✓  postman_collection/{service}.postman_collection.json")


# ─── 2. Mermaid Data Model (per API) ─────────────────────────────────────────

def _mermaid_class_diagram(api: dict) -> str:
    """Mermaid classDiagram for one API's domain entities."""
    entities = _safe_list((api.get("data_model") or {}).get("entities"))
    if not entities:
        return ""

    lines = ["```mermaid", "classDiagram"]

    for ent in entities:
        name   = re.sub(r'[^a-zA-Z0-9_]', '_', ent.get("name", ""))
        etype  = ent.get("type", "")
        fields = _safe_list(ent.get("fields"))

        lines.append(f"  class {name} {{")
        if etype:
            lines.append(f"    <<{etype}>>")
        for f in fields:
            fname     = f.get("field", "")
            ftype     = (f.get("type") or "String").replace(" ", "").replace("|", "_or_")
            nullable  = "?" if f.get("nullable", True) else ""
            enum_vals = _safe_str_list(f.get("enum_values"))
            comment   = f" // {', '.join(enum_vals)}" if enum_vals else ""
            lines.append(f"    {ftype}{nullable} {fname}{comment}")
        lines.append("  }")

    for ent in entities:
        name = re.sub(r'[^a-zA-Z0-9_]', '_', ent.get("name", ""))
        for rel in _safe_str_list(ent.get("relationships")):
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
                lines.append(arrow_map.get(rtype, f"  {left} --> {right}"))

    lines.append("```")
    return "\n".join(lines)


def generate_data_model_charts(cfg: Config, apis: List[dict]) -> None:
    """One Mermaid classDiagram per API → data_model/"""
    for api in apis:
        diagram = _mermaid_class_diagram(api)
        if not diagram:
            continue

        api_id  = api.get("api_id", "unknown")
        method  = api.get("method", "")
        path    = api.get("path", "")
        summary = (api.get("overview") or {}).get("summary", "")

        content = f"# Data Model — `{method}` {path}\n\n"
        if summary:
            content += f"_{summary}_\n\n"
        content += diagram + "\n"

        out_path = os.path.join(cfg.data_model_dir, f"{api_id}_datamodel.md")
        with open(out_path, "w") as f:
            f.write(content)
        print(f"   ✓  data_model/{api_id}_datamodel.md")


# ─── 3. ER Diagram (per SERVICE) ─────────────────────────────────────────────

def _mermaid_er_diagram(service_apis: List[dict]) -> str:
    """
    Mermaid erDiagram combining all entities across a service.
    Strict syntax: type fieldName "comment"
    No nullable/not_null keywords — not supported by Mermaid erDiagram.
    """
    entity_lines = []
    relation_lines = []
    seen = set()

    def clean_name(s: str) -> str:
        """Entity/field names: alphanumeric + underscore only."""
        return re.sub(r'[^a-zA-Z0-9_]', '_', s or "").strip('_') or "Unknown"

    def clean_type(s: str) -> str:
        """
        Field type: single word, no generics, no special chars.
        List<String> → List, Map<K,V> → Map, String? → String
        """
        s = (s or "String").split("<")[0].split("[")[0].split("|")[0].strip()
        s = re.sub(r'[^a-zA-Z0-9_]', '', s)
        return s or "String"

    def clean_comment(desc: str, enum_vals: list) -> str:
        """Short comment in double quotes — no quotes or newlines inside."""
        if enum_vals:
            raw = ", ".join(str(v) for v in enum_vals[:4])
        elif desc:
            raw = desc[:50]
        else:
            return ""
        # Strip characters that break Mermaid comment parsing
        raw = re.sub(r'["\n\r]', '', raw).strip()
        return f' "{raw}"' if raw else ""

    for api in service_apis:
        entities = _safe_list((api.get("data_model") or {}).get("entities"))
        for ent in entities:
            name = clean_name(ent.get("name", ""))
            if not name or name in seen:
                continue
            seen.add(name)

            fields = _safe_list(ent.get("fields"))
            ent_block = [f"  {name} {{"]
            for f in fields:
                fname   = clean_name(f.get("field", ""))
                ftype   = clean_type(f.get("type", "String"))
                comment = clean_comment(
                    f.get("description", ""),
                    _safe_str_list(f.get("enum_values"))
                )
                if fname:
                    ent_block.append(f"    {ftype} {fname}{comment}")
            ent_block.append("  }")
            entity_lines.extend(ent_block)

        # Relationships — labels must be quoted in erDiagram
        for ent in entities:
            name = clean_name(ent.get("name", ""))
            for rel in _safe_str_list(ent.get("relationships")):
                m = re.match(
                    r'(\w[\w\s]*)?\s*(hasMany|hasOne|extends|references|contains|belongsTo)\s+([\w\s]+)',
                    rel.strip(), re.IGNORECASE
                )
                if not m:
                    continue
                left  = clean_name((m.group(1) or name).strip())
                rtype = m.group(2).lower()
                right = clean_name(m.group(3).strip())
                er_map = {
                    "hasmany":    f'  {left} ||--o{{ {right} : "has"',
                    "hasonone":   f'  {left} ||--|| {right} : "has"',
                    "extends":    f'  {left} ||--|| {right} : "extends"',
                    "references": f'  {left} }}o--|| {right} : "references"',
                    "contains":   f'  {left} ||--|{{ {right} : "contains"',
                    "belongsto":  f'  {left} }}o--|| {right} : "belongs_to"',
                }
                line = er_map.get(rtype, f'  {left} }}o--o{{ {right} : "relates"')
                if line not in relation_lines:
                    relation_lines.append(line)

    if not entity_lines and not relation_lines:
        return ""

    lines = ["```mermaid", "erDiagram", ""]
    lines.extend(entity_lines)
    if relation_lines:
        lines.append("")
        lines.extend(relation_lines)
    lines.append("```")
    return "\n".join(lines)


def generate_er_diagrams(cfg: Config, apis: List[dict]) -> None:
    """One ER diagram per service → db_entity_relations/"""
    by_service = defaultdict(list)
    for api in apis:
        by_service[api.get("service", cfg.service)].append(api)

    for service, service_apis in by_service.items():
        er = _mermaid_er_diagram(service_apis)
        content  = f"# Entity Relationship Diagram — {service}\n\n"
        content += "_Combined DB schema across all documented APIs for this service_\n\n"
        content += er + "\n"

        out_path = os.path.join(cfg.db_er_dir, f"{service}_er_diagram.md")
        with open(out_path, "w") as f:
            f.write(content)
        print(f"   ✓  db_entity_relations/{service}_er_diagram.md")


# ─── 4. Swagger / OpenAPI 3.0 YAML (per SERVICE) ────────────────────────────

def _field_to_schema(f: dict) -> dict:
    """Convert an analysis field dict to an OpenAPI schema dict."""
    ftype   = (f.get("type") or "string").lower()
    nested  = _safe_list(f.get("nested_fields"))
    enum_vals = _safe_str_list(f.get("enum_values"))

    if nested:
        return {
            "type":        "object",
            "description": f.get("description", ""),
            "properties":  {n.get("field", ""): _field_to_schema(n) for n in nested},
        }

    schema: dict = {"description": f.get("description", "")}

    if "int" in ftype or "integer" in ftype:
        schema["type"] = "integer"
    elif "float" in ftype or "double" in ftype or "decimal" in ftype or "number" in ftype:
        schema["type"] = "number"
    elif "bool" in ftype:
        schema["type"] = "boolean"
    elif "array" in ftype or "list" in ftype:
        schema["type"]  = "array"
        schema["items"] = {"type": "string"}
    elif "object" in ftype or "map" in ftype or "dict" in ftype:
        schema["type"] = "object"
    else:
        schema["type"] = "string"

    if enum_vals:
        schema["enum"] = enum_vals

    example = f.get("example")
    if example not in (None, "", "string"):
        schema["example"] = example

    return schema


def _to_yaml(spec: dict) -> str:
    """
    Serialize OpenAPI spec to YAML.
    Uses PyYAML (installed with anthropic) for correct output.
    Falls back to JSON (valid YAML superset) if PyYAML unavailable.
    """
    try:
        import yaml

        class _NoAliasDumper(yaml.Dumper):
            """Prevents PyYAML from emitting anchors/aliases."""
            def ignore_aliases(self, data):
                return True

        return yaml.dump(
            spec,
            Dumper=_NoAliasDumper,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            indent=2,
            width=120,
        )
    except ImportError:
        # JSON is valid YAML — always works
        return json.dumps(spec, indent=2, ensure_ascii=False)


def _build_openapi(service: str, service_apis: List[dict]) -> dict:
    """Build an OpenAPI 3.0 spec dict from analysis JSON."""
    paths: dict = {}
    schemas: dict = {}

    for api in service_apis:
        method   = api.get("method", "GET").lower()
        path     = re.sub(r'\{([^}:]+)(?::[^}]*)?\}', r'{\1}', api.get("path", "/"))
        ov       = api.get("overview") or {}
        rq       = api.get("request") or {}
        rs       = api.get("response") or {}
        dm       = api.get("data_model") or {}
        api_id   = _slugify(api.get("api_id", ""))

        # Parameters
        parameters = []
        for pp in _safe_list(rq.get("path_params")):
            parameters.append({
                "name":        pp.get("name", ""),
                "in":          "path",
                "required":    True,
                "description": pp.get("description", ""),
                "schema":      {"type": "string"},
            })
        for qp in _safe_list(rq.get("query_params")):
            parameters.append({
                "name":        qp.get("name", ""),
                "in":          "query",
                "required":    qp.get("required", False),
                "description": qp.get("description", ""),
                "schema":      {"type": "string"},
            })
        for h in _safe_list(rq.get("headers")):
            if h.get("name", "").lower() not in ("content-type", "accept"):
                parameters.append({
                    "name":        h.get("name", ""),
                    "in":          "header",
                    "required":    h.get("required", False),
                    "description": h.get("description", ""),
                    "schema":      {"type": "string"},
                })

        # Request body
        request_body = None
        body = rq.get("body") or {}
        if isinstance(body, dict) and body.get("fields"):
            schema_name  = f"{api_id}_Request"
            props        = {f.get("field", ""): _field_to_schema(f)
                           for f in _safe_list(body["fields"])}
            required_flds = [f.get("field", "") for f in _safe_list(body["fields"])
                             if f.get("required")]
            schemas[schema_name] = {
                "type":        "object",
                "description": body.get("description", ""),
                "properties":  props,
            }
            if required_flds:
                schemas[schema_name]["required"] = required_flds

            request_body = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {"$ref": f"#/components/schemas/{schema_name}"}
                    }
                },
            }

        # Responses
        responses: dict = {}
        for s in _safe_list(rs.get("success")):
            code = str(s.get("status_code", 200))
            resp_fields = _safe_list(s.get("fields"))
            if resp_fields:
                schema_name = f"{api_id}_Response_{code}"
                schemas[schema_name] = {
                    "type":       "object",
                    "properties": {f.get("field", ""): _field_to_schema(f)
                                   for f in resp_fields},
                }
                responses[code] = {
                    "description": s.get("description", "Success"),
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{schema_name}"}
                        }
                    },
                }
            else:
                responses[code] = {"description": s.get("description", "Success")}

        for e in _safe_list(rs.get("errors")):
            code = str(e.get("status_code", 400))
            responses[code] = {"description": e.get("description", "Error")}

        if not responses:
            responses["200"] = {"description": "Success"}

        # Build operation
        operation: dict = {
            "summary":     ov.get("summary", ""),
            "description": ov.get("purpose", ""),
            "operationId": api_id,
            "tags":        [api.get("service", service)],
            "parameters":  parameters,
            "responses":   responses,
        }
        if request_body:
            operation["requestBody"] = request_body

        # Add entities to schemas
        for ent in _safe_list(dm.get("entities")):
            ent_name = _slugify(ent.get("name", ""))
            if ent_name and ent_name not in schemas:
                props = {f.get("field", ""): _field_to_schema(f)
                         for f in _safe_list(ent.get("fields"))}
                schemas[ent_name] = {
                    "type":        "object",
                    "description": ent.get("description", ""),
                    "properties":  props,
                }

        paths.setdefault(path, {})[method] = operation

    return {
        "openapi": "3.0.3",
        "info": {
            "title":       f"{service} API",
            "description": f"Auto-generated OpenAPI documentation for {service} by Doctor",
            "version":     "1.0.0",
        },
        "paths": paths,
        "components": {"schemas": schemas} if schemas else {},
    }


def generate_swagger(cfg: Config, apis: List[dict]) -> None:
    """One OpenAPI 3.0 YAML per service → api_document/"""
    by_service = defaultdict(list)
    for api in apis:
        by_service[api.get("service", cfg.service)].append(api)

    for service, service_apis in by_service.items():
        spec    = _build_openapi(service, service_apis)
        content = _to_yaml(spec)

        out_path = os.path.join(cfg.api_doc_dir, f"{service}_openapi.yaml")
        with open(out_path, "w") as f:
            f.write(content)
        print(f"   ✓  api_document/{service}_openapi.yaml")


# ─── Phase entry point ────────────────────────────────────────────────────────

def run(cfg: Config) -> None:
    print()
    apis = _load_analyses(cfg)

    if not apis:
        print("   ⚠️  No analysis files found — run Phase 2 first")
        return

    skip = cfg.skip
    print(f"   Generating artifacts for {len(apis)} APIs...\n")

    if "postman" not in skip:
        print("📮 Postman Collections")
        generate_postman(cfg, apis)
        print()

    if "datamodel" not in skip:
        print("📐 Data Model Charts (per API)")
        generate_data_model_charts(cfg, apis)
        print()

    if "er" not in skip:
        print("🗄️  ER Diagrams (per service)")
        generate_er_diagrams(cfg, apis)
        print()

    if "swagger" not in skip:
        print("📄 OpenAPI / Swagger YAML (per service)")
        generate_swagger(cfg, apis)
        print()

    active = [k for k in ["postman","datamodel","er","swagger"] if k not in skip]
    skipped = [k for k in ["postman","datamodel","er","swagger"] if k in skip]

    print("━" * 50)
    print("✅ Artifacts complete!")
    print("   output/")
    if "documents" not in skip: print("   ├── documents/            ← API docs (markdown)")
    if "datamodel" not in skip: print("   ├── data_model/           ← class diagrams")
    if "er"        not in skip: print("   ├── db_entity_relations/  ← ER diagrams")
    if "postman"   not in skip: print("   ├── postman_collection/   ← Postman collections")
    if "swagger"   not in skip: print("   └── api_document/         ← OpenAPI YAML")
    if skipped:
        print(f"   ⏭  Skipped: {', '.join(skipped)}")
    print("━" * 50)