# Doctor — API Documentation Skill

## What Doctor does
Doctor (DOCument creaTOR) auto-generates exhaustive API documentation from
source code. Given a GitHub repo or local codebase, it produces:
- Markdown docs per endpoint (request/response, blast radius, implementation detail)
- Postman collections per service
- Mermaid class diagrams per endpoint
- Mermaid ER diagrams per service
- OpenAPI 3.0 YAML per service

## When to invoke this skill
Use Doctor when the user asks to:
- "Document the APIs in this repo"
- "Generate API docs for <service>"
- "Create a Postman collection for <repo>"
- "Generate an OpenAPI spec for <service>"
- "Analyze the endpoints in <repo>"
- "Document these APIs"

## Prerequisites (check before running)
```bash
ls run.sh scripts/pipeline.py    # verify Doctor is installed
claude -p "say ok"               # verify Claude Code is authenticated
cat .env                         # verify .env is configured
```

If Doctor is not installed:
```bash
git clone https://github.com/mahulivishal/doctor.git
cd doctor
bash setup.sh
claude auth login
```

## Configuration

### .env (required)
```bash
SERVICE=my-service
BRANCH=main
REPO=https://your-token@github.com/your-org/your-repo.git
IS_MONOREPO=false
CLAUDE_MODEL=
ANTHROPIC_API_KEY=       # optional — enables token tracking
PARALLEL_WORKERS=4
```

### config/target-endpoints.yaml
```yaml
# Leave empty [] to document ALL endpoints
target_endpoints:
  - path: "/api/v1/orders"
    method: POST
    label: "Create Order"
```

### config/repos.yaml — monorepo only
```yaml
repo:
  services:
    - name: auth-service
      path: services/auth-service
```

## Running

```bash
bash run.sh                          # full reset + run
bash run.sh --from 3                 # resume from analysis
bash run.sh --from 5                 # regenerate artifacts only
bash run.sh --only 2                 # discovery only
bash run.sh --api <api_id>           # single endpoint
bash run.sh --skip postman           # skip specific artifact
bash run.sh --skip swagger --skip er # skip multiple
```

## Pipeline phases
| Phase | What happens | Claude calls |
|-------|-------------|-------------|
| 1 | Clone repo | 0 |
| 2 | Discover endpoints | 1 per service |
| 3 | Deep-analyze each endpoint (parallel) | 1 per endpoint |
| 4 | Render markdown docs | 0 |
| 5 | Generate Postman, Mermaid, ER, OpenAPI | 0 |
| 6 | Build master index | 0 |

## Output structure
```
output/
├── README.md                              # master index
├── documents/<api_id>.md                  # one doc per endpoint
├── data_model/<api_id>_datamodel.md       # Mermaid class diagram
├── db_entity_relations/<service>_er.md    # Mermaid ER diagram per service
├── postman_collection/<service>.json      # Postman collection
└── api_document/<service>_openapi.yaml    # OpenAPI 3.0 spec
```

## Supported languages
Java/Kotlin (Spring Boot), Python (FastAPI, Flask), Go (Gin, Echo, Chi, Fiber), Node (Express, NestJS)

## Using a local zip (no clone needed)
```bash
unzip repo.zip -d workspace/repos/<service-name>
bash run.sh --from 2
```

## Common issues
| Problem | Fix |
|---------|-----|
| 0 endpoints matched | Check path format in target-endpoints.yaml |
| Interactive Claude opens | Leave CLAUDE_MODEL empty in .env |
| PARSE_FAILED on all endpoints | Set ANTHROPIC_API_KEY to use SDK directly |
| Missing monorepo services | Check ls workspace/repos/<name>/ and fix repos.yaml paths |
