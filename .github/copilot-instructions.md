# Doctor — Copilot Instructions

Doctor (DOCument creaTOR) auto-generates API documentation from source code.
This file tells GitHub Copilot how to help users work with Doctor.

## Project structure
- `run.sh` — entry point, runs the full pipeline
- `scripts/pipeline.py` — master orchestrator
- `scripts/config.py` — loads .env, repos.yaml, target-endpoints.yaml
- `scripts/discover.py` — finds all API endpoints (Claude-powered)
- `scripts/analyze.py` — deep-analyzes each endpoint (Claude-powered, parallel)
- `scripts/render.py` — converts JSON analysis to Markdown
- `scripts/artifacts.py` — generates Postman collections and Mermaid diagrams
- `scripts/assemble.py` — builds master index and ACL checklist
- `config/.env` — user config (not committed)
- `config/repos.yaml` — repo and service definitions
- `config/target-endpoints.yaml` — endpoint whitelist

## Key conventions
- All orchestration is Python, git operations are bash
- Analysis JSON lives in `workspace/analysis/<api_id>.json`
- Output docs live in `output/docs/<api_id>.md`
- `_safe_list()` and `_safe_str_list()` must be used for all list access from analysis JSON
- Claude is only invoked in `discover.py` and `analyze.py` via `subprocess.run`
- Prompt strings are plain Python strings, never shell-interpolated
- API IDs are slugified: `re.sub(r'[^a-zA-Z0-9_-]', '_', raw_id)`

## Analysis JSON schema (workspace/analysis/<api_id>.json)
Every analysis file must contain these 9 top-level keys:
`api_id`, `service`, `method`, `path`, `overview`, `request`, `response`,
`blast_radius`, `implementation_detail`

Optional but important: `data_model`, `functional_mapping`

## Request body schema (new format)
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

## When helping with Doctor code
- Adding a new output format → add a function to `artifacts.py` and call it from `run()`
- Adding a new language → update the discovery prompt in `discover.py` DISCOVERY_PROMPT
- Changing doc structure → update `render.py` render() function
- Changing what Claude analyzes → update `analyze.py` ANALYSIS_PROMPT_TEMPLATE
- Adding a new pipeline phase → add phase function in `pipeline.py`, wire into `main()`

## Running
```bash
bash run.sh                  # full run
bash run.sh --from 3         # resume from analysis
bash run.sh --only 2         # discovery only
bash run.sh --api <api_id>   # single endpoint
```