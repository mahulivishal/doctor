# Doctor

> **DOCument creaTOR** — A Python-orchestrated Claude Code framework that auto-generates exhaustive API documentation directly from source code. Point it at any GitHub repo or local codebase and it produces production-ready docs, diagrams, and API specs in minutes.

---

## Three ways to run Doctor

| Mode | How | Best for |
|---|---|---|
| **Terminal** | `bash run.sh` | Local development, one-off runs |
| **API** | `POST /run` | CI/CD — GitHub Actions, GitLab CI, Azure Pipelines |
| **SKILL** | Claude Code reads `SKILL.md` | Autonomous AI-driven documentation |

All three modes run the same pipeline. Only config loading differs.

---

## What it produces

For every targeted HTTP endpoint:

| Section | What it contains |
|---|---|
| **Overview** | Summary, business purpose, context, integration notes |
| **Request** | Every field fully expanded — types, validation, enum values, nested objects |
| **Response** | Fields, error codes with exact trigger conditions |
| **Field Transformations** | Only populated when actual transformations exist |
| **Blast Radius** | Severity, downstream consumers, upstream dependencies, side effects |
| **Implementation Details** | End-to-end narrative + explanatory bullet points |

Plus per-service artifacts:

| Artifact | Location |
|---|---|
| API markdown docs | `output/documents/<api_id>.md` |
| Mermaid class diagrams | `output/data_model/<api_id>_datamodel.md` |
| ER diagram (per service) | `output/db_entity_relations/<service>_er_diagram.md` |
| Postman collection | `output/postman_collection/<service>.postman_collection.json` |
| OpenAPI 3.0 YAML | `output/api_document/<service>_openapi.yaml` |

---

## Project structure

```
doctor/
|
+-- run.sh                          # Terminal entry point
+-- setup.sh                        # One-time setup
+-- validate.sh                     # Pre-flight checks
+-- SKILL.md                        # Claude Code skill
+-- CLAUDE.md                       # Agent instructions
+-- requirements.txt                # Python dependencies
+-- .env                            # Your config (never commit)
+-- .env.template                   # Template to copy from
|
+-- config/
|   +-- repos.yaml
|   +-- target-endpoints.yaml
|   +-- .claudeignore
|
+-- scripts/
|   +-- pipeline.py                 # Master orchestrator (all 3 modes)
|   +-- config.py                   # Config loader: load() and load_from_dict()
|   +-- token_tracker.py            # Token usage accumulator
|   +-- clone.py                    # VCS-agnostic cloning + PR branch creation
|   +-- discover.py                 # Phase 2: endpoint discovery
|   +-- analyze.py                  # Phase 3: deep analysis (parallel)
|   +-- render.py                   # Phase 4: JSON to Markdown
|   +-- artifacts.py                # Phase 5: Postman, Mermaid, ER, OpenAPI
|   +-- pr.py                       # PR creation via httpx (no VCS SDK)
|   +-- server.py                   # FastAPI server (API mode)
|   +-- run_manager.py              # Concurrent run tracking
|
+-- docker/
|   +-- Dockerfile
|   +-- docker-compose.yml
|   +-- k8s/
|       +-- deployment.yaml
|       +-- service-hpa.yaml
|
+-- workspace/
    +-- runs/
        +-- <run_id>/               # Isolated workspace per run
            +-- repos/
            +-- manifests/
            +-- analysis/
            +-- output/
                +-- documents/
                +-- data_model/
                +-- db_entity_relations/
                +-- postman_collection/
                +-- api_document/
```

---

## Terminal mode

### Setup
```bash
git clone https://github.com/mahulivishal/doctor.git
cd doctor
pip install -r requirements.txt
bash setup.sh
claude auth login
```

### Configure
```bash
cp .env
# Edit .env: SERVICE, REPO, VCS_PROVIDER, token
```

### Run
```bash
bash run.sh                            # full run
bash run.sh --from 3                   # resume from analysis
bash run.sh --from 5                   # regenerate artifacts only
bash run.sh --only 2                   # discovery only
bash run.sh --api <api_id>             # single endpoint
bash run.sh --raise-pr                 # generate and raise PR
bash run.sh --skip postman             # skip an artifact
bash run.sh --skip swagger --skip er   # skip multiple
bash run.sh --run-id <id>              # resume existing run workspace
```

---

## API mode

### Start the server
```bash
# Local
uvicorn scripts.server:app --host 0.0.0.0 --port 8000

# Docker
docker-compose -f docker/docker-compose.yml up

# Kubernetes
kubectl apply -f docker/k8s/
```

### Endpoints

| Method | Path | Description |
|---|---|---|
| GET | /health | Liveness check (no auth) |
| POST | /run | Start a run, returns run_id immediately (202) |
| GET | /run/{run_id} | Poll status and progress |
| GET | /run/{run_id}/output | Download output as zip |
| POST | /run/{run_id}/pr | Manually raise PR for completed run |
| DELETE | /run/{run_id} | Delete run state |
| GET | /runs | List all runs |

All endpoints except /health require: `X-Doctor-Key: your-api-key`

### Trigger from CI/CD (same call works everywhere)
```bash
curl -X POST https://doctor.yourserver.com/run \
  -H "X-Doctor-Key: $DOCTOR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "service":          "my-service",
    "repo":             "https://github.com/org/my-service.git",
    "branch":           "main",
    "vcs_provider":     "github",
    "vcs_token":        "ghp_...",
    "parallel_workers": 4,
    "target_endpoints": [
      {"path": "/api/v1/orders", "method": "POST", "label": "Create Order"}
    ],
    "raise_pr": true
  }'
```

### Poll for completion
```bash
curl https://doctor.yourserver.com/run/<run_id> \
  -H "X-Doctor-Key: $DOCTOR_API_KEY"
```
```json
{
  "run_id":          "a3f9b2",
  "status":          "running",
  "current_phase":   3,
  "phase_label":     "Analyzing endpoints",
  "endpoints_total": 8,
  "endpoints_done":  3,
  "pr_url":          null,
  "elapsed_seconds": 142.3
}
```

---

## SKILL mode (Claude Code)

```bash
cd doctor
claude
```

Tell Claude what you want:
- "Document the APIs in https://github.com/org/my-service.git"
- "Generate an OpenAPI spec for the accounting service"
- "Document these 4 endpoints and raise a PR"

Claude reads SKILL.md and runs the pipeline autonomously.

---

## VCS providers

| Provider | .env token key | Notes |
|---|---|---|
| GitHub | GITHUB_TOKEN | Personal access token |
| GitLab cloud | GITLAB_TOKEN | glpat-... token |
| GitLab self-hosted | GITLAB_TOKEN + VCS_BASE_URL | Set VCS_BASE_URL to your instance |
| Azure Repos | AZURE_TOKEN | Personal access token |
| Bitbucket | BITBUCKET_TOKEN | Repository access token |

### Self-hosted GitLab example
```bash
VCS_PROVIDER=gitlab
GITLAB_TOKEN=glpat-...
VCS_BASE_URL=https://git.your-company.com
REPO=https://git.your-company.com/org/repo.git
```

---

## Pull Requests

After generating documentation, Doctor can raise a PR back to the source repo.

Branch name: `doctor/<service>-<YYYY-MM-DD>-<run_id>`
Output location in repo: `docs/doctor/<service>/`

```bash
# Terminal
bash run.sh --raise-pr

# .env
RAISE_PR=true

# API request body
{"raise_pr": true}
```

PR is only raised if Phase 1 (clone) ran in the current run.

---

## Run isolation

Every run gets a unique run_id and isolated workspace under `workspace/runs/<run_id>/`.
Multiple runs coexist without interfering. Terminal run_id defaults to a timestamp.

---

## Configuration reference

| Field | Default | Description |
|---|---|---|
| SERVICE | required | Service name |
| REPO | required | Clone URL |
| BRANCH | main | Branch to clone |
| VCS_PROVIDER | github | github / gitlab / azure / bitbucket |
| GITHUB_TOKEN | | GitHub personal access token |
| GITLAB_TOKEN | | GitLab personal access token |
| AZURE_TOKEN | | Azure DevOps token |
| BITBUCKET_TOKEN | | Bitbucket token |
| VCS_BASE_URL | | Self-hosted VCS base URL |
| IS_MONOREPO | false | Multi-service repo |
| CLAUDE_MODEL | | Leave empty for default |
| ANTHROPIC_API_KEY | | Optional, enables token tracking |
| PARALLEL_WORKERS | 4 | Endpoints analyzed simultaneously |
| RAISE_PR | false | Auto-raise PR after generation |
| PR_BASE_BRANCH | BRANCH | Target branch for PR |
| DOCTOR_API_KEY | | Server mode API auth key |

---

## Pipeline phases

| Phase | Description | Claude calls |
|---|---|---|
| 1 | Clone repo via VCS provider | 0 |
| 2 | Discover all endpoints | 1 per service |
| 3 | Deep-analyze each endpoint (parallel) | 1 per endpoint |
| 4 | Render markdown docs | 0 |
| 5 | Generate Postman, Mermaid, ER, OpenAPI | 0 |
| PR | Commit output + raise PR | 0 |

---

## Supported languages and frameworks

Java/Kotlin (Spring Boot), Python (FastAPI, Flask), Go (Gin, Echo, Chi, Fiber, net/http), TypeScript/JavaScript (Express, NestJS)

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Cannot reach repo | Check VCS token, VCS_BASE_URL, network |
| claude not found | npm install -g @anthropic-ai/claude-code |
| PARSE_FAILED on all endpoints | Set ANTHROPIC_API_KEY to bypass Claude Code CLI |
| 0 endpoints matched | Check path format in target-endpoints.yaml |
| PR creation 401 | Token needs write access (repo scope for GitHub) |
| PR skipped | Must run from Phase 1 (--from 1 or fresh run.sh) |