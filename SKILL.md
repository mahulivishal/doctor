# Doctor — API Documentation Skill

## What Doctor does
Doctor (DOCument creaTOR) is a Claude Code framework that auto-generates
exhaustive API documentation from source code. Given a GitHub repository,
it produces:
- Markdown docs per endpoint (request/response, data model, blast radius, ACL notes)
- Postman collections
- Mermaid class diagrams and ER diagrams
- Master index and ACL implementation checklist

## When to invoke this skill
Use Doctor when the user asks to:
- "Document the APIs in this repo"
- "Generate API docs for <service>"
- "Create a Postman collection for <repo>"
- "Analyze the endpoints in <repo>"
- "Document these APIs for ACL migration"

## Prerequisites (check before running)
```bash
# Verify Doctor is installed
ls run.sh scripts/pipeline.py

# Verify Claude Code is authenticated
claude -p "say ok"

# Verify .env is configured
cat .env
```

If Doctor is not installed:
```bash
git clone https://github.com/mahulivishal/doctor.git
cd doctor
bash setup.sh
```

## Configuration files to set up

### .env
```bash
SERVICE=<repo-name>
BRANCH=main
REPO=https://<token>@github.com/<org>/<repo>.git
IS_MONOREPO=false          # true if repo has multiple services
CLAUDE_MODEL=              # leave empty for default
PARALLEL_WORKERS=4
```

### config/repos.yaml — single repo
```yaml
repo:
  name: <service-name>
  api_paths:
    - src/main/java      # Java/Kotlin
    - src/main/kotlin
    - app/               # Python
    - internal/          # Go
```

### config/repos.yaml — monorepo
```yaml
repo:
  services:
    - name: auth-service
      path: services/auth-service
    - name: order-service
      path: services/order-service
```

### config/target-endpoints.yaml
```yaml
# Leave empty [] to document ALL endpoints
target_endpoints:
  - path: "/api/v1/orders"
    method: POST
    acl_priority: HIGH
    label: "Create Order"
  - path: "/api/v1/orders/{id}"
    method: GET
    acl_priority: MEDIUM
    label: "Get Order"
```

## Running Doctor

### Full pipeline (reset + run everything)
```bash
bash run.sh
```

### Resume from a specific phase
```bash
bash run.sh --from 2    # re-run discovery onwards
bash run.sh --from 3    # re-run analysis onwards (skip clone + discovery)
bash run.sh --from 4    # re-render docs only (no Claude calls)
bash run.sh --from 5    # regenerate artifacts only
```

### Single endpoint
```bash
bash run.sh --api <api_id>
```

### Only one phase
```bash
bash run.sh --only 2    # discovery only — see all endpoints before analyzing
```

## Pipeline phases
| Phase | What happens | Claude calls |
|-------|-------------|-------------|
| 1 | Clone repo (shallow, depth=1) | 0 |
| 2 | Discover all endpoints, filter to targets | 1 per service |
| 3 | Deep-analyze each endpoint in parallel | 1 per endpoint |
| 4 | Render markdown docs | 0 |
| 5 | Generate Postman + Mermaid diagrams | 0 |
| 6 | Build master index + ACL checklist | 0 |

## Output structure
```
output/
├── README.md                    # master index, blast radius table
├── ACL-CHECKLIST.md             # implementation order, transform catalogue
├── api-registry.json            # machine-readable registry
├── docs/
│   └── <api_id>.md              # one doc per endpoint
├── postman/
│   └── <service>.postman_collection.json
└── diagrams/
    ├── <api_id>_datamodel.md    # Mermaid class diagram per API
    └── <service>_er_diagram.md  # Mermaid ER diagram per service
```

## Supported languages and frameworks
- **Java/Kotlin**: Spring Boot (@GetMapping, @PostMapping, @RequestMapping)
- **Python**: FastAPI (@router.get, @app.post), Flask (@app.route)
- **Go**: Gin, Echo, Chi, Fiber, net/http
- **Node**: Express, NestJS

## Common issues
| Problem | Fix |
|---------|-----|
| 0 endpoints matched | Check target-endpoints.yaml path format matches router exactly |
| Interactive Claude session opens | CLAUDE_MODEL value is invalid — leave it empty |
| Analysis fails validation | Re-run: `bash run.sh --from 3` — retry logic handles it |
| Missing services in monorepo | Run `ls workspace/repos/<service>/` to find real directory names |