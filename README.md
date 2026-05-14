# Doctor

> **DOCument creaTOR** — A Python-orchestrated Claude Code framework that auto-generates exhaustive API documentation directly from source code. Point it at any GitHub repo or local codebase and it produces production-ready docs, diagrams, and API specs in minutes.

---

## What it produces

For every targeted HTTP endpoint, Doctor generates a comprehensive markdown document containing:

| Section | What it contains |
|---|---|
| **Overview** | Precise summary, business purpose, system context, integration notes |
| **Request** | Every header, path param, query param, and body field — fully expanded with types, validation constraints, enum values, and nested objects |
| **Response** | Success response fields with examples, all error codes with exact trigger conditions |
| **Field Transformations** | Field-level transformations applied by the endpoint — omitted if fields pass through unchanged |
| **Blast Radius** | Severity (HIGH/MEDIUM/LOW), downstream consumers, upstream dependencies, data mutation and side effects |
| **Implementation Detail** | Handler, middleware chain, auth mechanism, caching strategy, external calls, validation logic, notable logic, ambiguities |

In addition, Doctor generates the following artifacts per service:

| Artifact | Location | Description |
|---|---|---|
| **API Document** | `output/documents/<api_id>.md` | Full markdown doc per endpoint |
| **Data Model Chart** | `output/data_model/<api_id>_datamodel.md` | Mermaid `classDiagram` per endpoint |
| **ER Diagram** | `output/db_entity_relations/<service>_er_diagram.md` | Mermaid `erDiagram` — combined DB schema per service |
| **Postman Collection** | `output/postman_collection/<service>.postman_collection.json` | Ready-to-import Postman collection |
| **OpenAPI Spec** | `output/api_document/<service>_openapi.yaml` | OpenAPI 3.0.3 YAML for any developer portal |

> **Visualising diagrams:** Open `.md` files in VS Code with the [Mermaid Preview](https://marketplace.visualstudio.com/items?itemName=bierner.markdown-mermaid) extension (`Cmd+Shift+V`), push to GitHub (renders natively), or paste into [mermaid.live](https://mermaid.live).

---

## Project structure

```
doctor/
│
├── run.sh                          # Entry point — delegates to pipeline.py
├── setup.sh                        # One-time workbench setup
├── validate.sh                     # Pre-flight checks
├── SKILL.md                        # Claude Code skill — enables autonomous usage
├── CLAUDE.md                       # Agent instructions (auto-loaded by Claude Code)
│
├── .env                            # Your config (never commit this)
├── .env.template                   # Template to copy from
├── .gitignore                      # Ignores .env, workspace/, output/
│
├── .github/
│   └── copilot-instructions.md     # GitHub Copilot skill for Doctor contributors
│
├── config/
│   ├── repos.yaml                  # Repo + service path definitions (monorepo support)
│   ├── target-endpoints.yaml       # Endpoint whitelist (empty = document all)
│   └── .claudeignore               # Files Claude should never read
│
├── scripts/
│   ├── pipeline.py                 # Master orchestrator — 6 phases
│   ├── config.py                   # Central config loader
│   ├── token_tracker.py            # Thread-safe token usage accumulator
│   ├── discover.py                 # Phase 2: Discover endpoints per service
│   ├── analyze.py                  # Phase 3: Deep-analyze each endpoint (parallel)
│   ├── render.py                   # Phase 4: JSON → Markdown (parallel, no Claude)
│   ├── artifacts.py                # Phase 5: Postman, Mermaid, ER, OpenAPI (no Claude)
│   ├── assemble.py                 # Phase 6: Master index
│   └── 1-clone-repo.sh             # Phase 1: Git clone (bash)
│
├── workspace/                      # Intermediate files (safe to delete)
│   ├── repos/<service>/            # Cloned or extracted repo
│   ├── manifests/                  # Discovered endpoint manifests
│   └── analysis/                   # Raw Claude analysis JSON per endpoint
│
└── output/
    ├── documents/
    │   └── <api_id>.md             # One comprehensive doc per endpoint
    ├── data_model/
    │   └── <api_id>_datamodel.md   # Mermaid class diagram per endpoint
    ├── db_entity_relations/
    │   └── <service>_er_diagram.md # Mermaid ER diagram per service
    ├── postman_collection/
    │   └── <service>.postman_collection.json
    └── api_document/
        └── <service>_openapi.yaml  # OpenAPI 3.0.3 spec per service
```

---

## Quickstart

```bash
# 1. Clone Doctor
git clone https://github.com/mahulivishal/doctor.git
cd doctor

# 2. One-time setup
bash setup.sh

# 3. Authenticate Claude Code
claude auth login

# 4. Configure
cp .env.template .env
# Edit .env with your repo URL, credentials, and model preference

# 5. Verify
bash validate.sh

# 6. Run
bash run.sh
```

---

## Configuration

### `.env`

```bash
# Repo
SERVICE=my-service
BRANCH=main
REPO=https://your-token@github.com/your-org/your-repo.git

# Monorepo — set true if repo has multiple services in subdirectories
IS_MONOREPO=false

# Claude model — leave empty to use Claude Code default
CLAUDE_MODEL=

# Token tracking — optional, enables token usage reporting
# Get your key at: https://console.anthropic.com/settings/keys
ANTHROPIC_API_KEY=

# Parallel workers
PARALLEL_WORKERS=4
```

### `config/repos.yaml`

**Single repo:**
```yaml
repo:
  name: my-service
  api_paths:
    - src/main/java
    - src/main/kotlin
```

**Monorepo (set `IS_MONOREPO=true`):**
```yaml
repo:
  services:
    - name: auth-service
      path: services/auth-service
    - name: order-service
      path: services/order-service
```

### `config/target-endpoints.yaml`

```yaml
# Leave empty [] to document ALL endpoints
target_endpoints:
  - path: "/api/v1/orders"
    method: POST
    acl_priority: HIGH
    label: "Create Order"
    # service_name: order-service  # only needed for monorepos
```

---

## Running

```bash
# Full reset + run
bash run.sh

# Resume from a specific phase
bash run.sh --from 3      # re-run analysis onwards
bash run.sh --from 4      # re-render docs only
bash run.sh --from 5      # regenerate artifacts only

# Run only one phase
bash run.sh --only 2      # discovery only

# Single endpoint
bash run.sh --api <api_id>

# Skip specific output artifacts
bash run.sh --skip postman
bash run.sh --skip swagger
bash run.sh --skip er
bash run.sh --skip datamodel
bash run.sh --skip docs
bash run.sh --skip postman --skip swagger   # multiple

# Skip reset
bash run.sh --no-reset
```

---

## Using a local zip instead of cloning

```bash
unzip your-repo.zip -d workspace/repos/your-service-name
bash run.sh --from 2
```

---

## Token tracking

If `ANTHROPIC_API_KEY` is set in `.env`, Doctor uses the Anthropic SDK directly and prints a token summary after every run:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Token Usage
   API calls:     9
   Input tokens:  142,831
   Output tokens: 18,204
   Total tokens:  161,035

   Rate limit window (per minute):
   Remaining: 58,204 tokens  (29.1% available)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Without an API key, Doctor falls back to `claude -p` via Claude Code and token tracking is disabled.

---

## Supported languages and frameworks

| Language | Frameworks |
|---|---|
| Java | Spring Boot (`@GetMapping`, `@PostMapping`, `@RequestMapping`) |
| Kotlin | Spring Boot (same annotations) |
| Python | FastAPI, Flask |
| Go | Gin, Echo, Chi, Fiber, net/http |
| TypeScript / JavaScript | Express, NestJS |

---

## Pipeline phases

| Phase | Script | Claude calls | Description |
|---|---|---|---|
| 1 | `1-clone-repo.sh` | 0 | Shallow clone + strip noise |
| 2 | `discover.py` | 1 per service | Find all endpoints |
| 3 | `analyze.py` | 1 per endpoint | Deep analysis (parallel) |
| 4 | `render.py` | 0 | JSON → Markdown |
| 5 | `artifacts.py` | 0 | Postman, Mermaid, ER, OpenAPI |
| 6 | `assemble.py` | 0 | Master index |

---

## Using with Claude Code

Open Claude Code inside the `doctor/` directory and describe what you want:

```bash
cd doctor
claude
```

> *"Document the APIs in https://github.com/my-org/my-service.git"*

Claude reads `SKILL.md` and handles the entire workflow autonomously.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `claude: command not found` | `npm install -g @anthropic-ai/claude-code` |
| Auth error | `claude auth login` |
| 0 endpoints matched | Check path format in `target-endpoints.yaml` |
| Interactive Claude session opens | Leave `CLAUDE_MODEL` empty in `.env` |
| PARSE_FAILED on all endpoints | Set `ANTHROPIC_API_KEY` to use SDK directly |
| Missing monorepo services | Run `ls workspace/repos/<service>/` and update `repos.yaml` |
| `Config has no attribute claude_bin` | Add `claude_bin` back to `Config` dataclass in `config.py` |