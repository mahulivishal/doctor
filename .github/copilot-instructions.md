# Doctor — Copilot Instructions

Doctor (DOCument creaTOR) auto-generates API documentation from source code.
This file tells GitHub Copilot how to help developers work on Doctor itself.

## Project structure
- `run.sh` — entry point, calls pipeline.py
- `scripts/pipeline.py` — master orchestrator, 6 phases
- `scripts/config.py` — loads .env, repos.yaml, target-endpoints.yaml into Config dataclass
- `scripts/token_tracker.py` — thread-safe token accumulator, shared across parallel calls
- `scripts/discover.py` — Phase 2: finds all API endpoints (Claude/SDK)
- `scripts/analyze.py` — Phase 3: deep-analyzes each endpoint (Claude/SDK, parallel)
- `scripts/render.py` — Phase 4: JSON → Markdown (pure Python, parallel)
- `scripts/artifacts.py` — Phase 5: Postman, Mermaid, ER, OpenAPI (pure Python)
- `scripts/assemble.py` — Phase 6: builds master index README
- `scripts/1-clone-repo.sh` — Phase 1: git clone (bash only)

## Key conventions
- Claude is only invoked in `discover.py` and `analyze.py`
- If `cfg.api_key` is set → use Anthropic SDK + token tracking
- If `cfg.api_key` is empty → use `subprocess claude -p` via Claude Code CLI
- All list access from analysis JSON uses `_safe_list()` / `_safe_str_list()`
- API IDs are always slugified: `re.sub(r'[^a-zA-Z0-9_-]', '_', raw_id)`
- Path params normalized: `{param:.+}` → `{param}` → `{P}` for matching
- Comments stripped from yaml before regex parsing (prevents false matches)

## Config dataclass (config.py)
```python
@dataclass
class Config:
    service: str
    repo: str
    branch: str
    repo_root: str
    is_monorepo: bool
    services: List[ServiceConfig]
    api_key: str           # ANTHROPIC_API_KEY — empty string if not set
    claude_bin: str        # path to claude CLI
    claude_model: str
    parallel_workers: int
    skip: Set[str]         # subset of: docs, datamodel, er, postman, swagger
    target_endpoints: List[TargetEndpoint]
    project_root: str
    analysis_dir: str
    manifests_dir: str
    output_dir: str
    docs_dir: str          # output/documents/
    data_model_dir: str    # output/data_model/
    db_er_dir: str         # output/db_entity_relations/
    postman_dir: str       # output/postman_collection/
    api_doc_dir: str       # output/api_document/
```

## Analysis JSON schema (workspace/analysis/<api_id>.json)
Required top-level keys:
`api_id`, `service`, `method`, `path`, `overview`, `request`, `response`,
`blast_radius`, `implementation_detail`

Optional: `data_model`, `functional_mapping`

### Request body (new format — fields array, not schema/example)
```json
{
  "body": {
    "content_type": "application/json",
    "description": "...",
    "fields": [
      {
        "field": "fieldName",
        "type": "string|int|boolean|object|array",
        "required": true,
        "description": "...",
        "validation": "...",
        "example": "...",
        "enum_values": [],
        "nested_fields": []
      }
    ]
  }
}
```

## Output structure
```
output/
├── README.md
├── documents/<api_id>.md
├── data_model/<api_id>_datamodel.md
├── db_entity_relations/<service>_er_diagram.md
├── postman_collection/<service>.postman_collection.json
└── api_document/<service>_openapi.yaml
```

## Skip options
Valid values for `--skip` flag and `cfg.skip` set:
`docs`, `datamodel`, `er`, `postman`, `swagger`

## Extending Doctor
- **New output format** → add function to `artifacts.py`, call from `run()`, add skip key to `SKIP_OPTIONS` in `config.py`
- **New language** → update `DISCOVERY_PROMPT` in `discover.py`
- **Change doc sections** → update `render.py` `render()` function
- **Change what Claude analyzes** → update `ANALYSIS_PROMPT_TEMPLATE` in `analyze.py`
- **New pipeline phase** → add phase function in `pipeline.py`, wire into `main()`

## Token tracking
`token_tracker.py` exports a global `tracker` singleton.
Call `tracker.add(input_tokens, output_tokens)` after each SDK response.
Call `tracker.summary()` at end of run to print usage report.
Only populated when `cfg.api_key` is set and SDK path is used.

## Running
```bash
bash run.sh                    # full run
bash run.sh --from 3           # resume from analysis
bash run.sh --only 2           # discovery only
bash run.sh --api <api_id>     # single endpoint
bash run.sh --skip postman     # skip artifact
```
