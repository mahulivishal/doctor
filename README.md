# project doctor

> A Python-orchestrated Claude Code framework that auto-generates exhaustive API documentation for ACL layer implementation during OMS migration. Supports single repos, monorepos, and services written in Java, Kotlin, Python, and Go.

---
## What it produces

For every targeted HTTP endpoint, the framework outputs:

| Section | What it contains |
|---|---|
| **Overview** | Precise summary, business purpose, system context, integration notes |
| **Request** | Every header, path param, query param, and body field — fully expanded with types, validation constraints, enum values, and nested objects |
| **Response** | Success response fields with examples, all error codes with exact trigger conditions |
| **Field Transformations** | Only populated when real transformations exist (type casts, enum remaps, renames) — omitted for pass-through fields |
| **Blast Radius** | Severity (HIGH/MEDIUM/LOW), downstream consumers, upstream dependencies, data mutation and side effects |
| **Implementation Detail** | Handler, middleware chain, auth mechanism, caching strategy, all external calls, validation logic, notable logic, ambiguities |

These are compiled into the following output folders:

```
output/
├── documents/            ← One markdown doc per API endpoint
├── data_model/           ← One Mermaid class diagram per API endpoint
├── db_entity_relations/  ← One Mermaid ER diagram per service (full DB schema view)
├── postman_collection/   ← One Postman collection per service
└── api_document/         ← One OpenAPI 3.0 YAML per service
```

| Artifact | Description |
|---|---|
| `documents/<api_id>.md` | Full holistic documentation for one endpoint |
| `data_model/<api_id>_datamodel.md` | Mermaid `classDiagram` — domain entities, typed fields, enum values, relationships |
| `db_entity_relations/<service>_er_diagram.md` | Mermaid `erDiagram` — combined DB schema across all documented APIs for the service |
| `postman_collection/<service>.postman_collection.json` | Ready-to-import Postman collection with pre-filled bodies, example responses, and `{{base_url}}` variable |
| `api_document/<service>_openapi.yaml` | OpenAPI 3.0.3 spec — paste into Swagger UI, Redoc, Stoplight, or any developer portal |

Plus two summary files at `output/` root:

| File | Description |
|---|---|
| `README.md` | Master index table of all APIs with blast radius summary |
| `CHECKLIST.md` | Implementation priority guide and field transformation catalogue |
| `api-registry.json` | Machine-readable registry for tooling integration |

> **Visualising Mermaid diagrams:** Open `.md` files in VS Code with the [Mermaid Preview](https://marketplace.visualstudio.com/items?itemName=bierner.markdown-mermaid) extension (`Cmd+Shift+V`), push to GitHub (renders natively since 2022), or paste into [mermaid.live](https://mermaid.live).

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
│   ├── config.py                   # Central config loader (reads .env + yaml files)
│   ├── discover.py                 # Phase 2: Claude discovers endpoints per service
│   ├── analyze.py                  # Phase 3: Claude deep-analyzes each endpoint (parallel)
│   ├── render.py                   # Phase 4: JSON → Markdown docs (parallel, no Claude)
│   ├── artifacts.py                # Phase 5: Postman + Mermaid + ER + OpenAPI (no Claude)
│   ├── assemble.py                 # Phase 6: Master index, checklist, registry
│   └── 1-clone-repo.sh             # Phase 1: Git clone (bash — git stays in bash)
│
├── workspace/                      # Intermediate files (safe to delete and regenerate)
│   ├── repos/<service>/            # Cloned or extracted repo
│   ├── manifests/                  # Discovered endpoint manifests per service
│   └── analysis/                   # Raw Claude analysis JSON per endpoint
│
└── output/                         # Final deliverables
    ├── README.md                   # Master index with blast radius table
    ├── CHECKLIST.md                # Priority guide + field transformation catalogue
    ├── api-registry.json           # Machine-readable registry
    ├── documents/
    │   └── <api_id>.md             # One holistic doc per endpoint
    ├── data_model/
    │   └── <api_id>_datamodel.md   # Mermaid class diagram per endpoint
    ├── db_entity_relations/
    │   └── <service>_er_diagram.md # Mermaid ER diagram per service
    ├── postman_collection/
    │   └── <service>.postman_collection.json
    └── api_document/
        └── <service>_openapi.yaml  # OpenAPI 3.0 spec per service
```
---

## Quickstart

```bash
# 1. One-time setup
bash setup.sh

# 2. Authenticate Claude Code
claude auth login

# 3. Configure
cp .env.template .env
# Edit .env with your repo URL, credentials, and model preference

# 4. Verify environment
bash validate.sh

# 5. Run
bash run.sh
```

---

## Configuration

### `.env`

```bash
# ── Repo ─────────────────────────────────────────────────────────────────
SERVICE=product-config
BRANCH=main
REPO=https://your-username:your-token@git.company.com/org/repo.git

# ── Monorepo ──────────────────────────────────────────────────────────────
# Set to true if the repo contains multiple services in subdirectories
IS_MONOREPO=false

# ── Claude Model ──────────────────────────────────────────────────────────
# Leave empty to use Claude Code's default model
# Or set a specific model if your Claude Code version supports --model
CLAUDE_MODEL=

# ── Parallelism ───────────────────────────────────────────────────────────
# Number of endpoints to analyze simultaneously
PARALLEL_WORKERS=4
```

### `config/repos.yaml`

**Single repo:**
```yaml
repo:
  name: product-config
  api_paths:
    - src/main/java
    - src/main/kotlin
```

**Monorepo (set `IS_MONOREPO=true` in `.env`):**
```yaml
repo:
  services:
    - name: auth-service
      path: services/auth-service-v2
      api_paths:
        - app/

    - name: nmt-service
      path: services/nmt-service
      api_paths:
        - app/
```

### `config/target-endpoints.yaml`

```yaml
# Leave target_endpoints empty ([]) to document ALL discovered endpoints.
# For monorepos, add service_name to target a specific service.

target_endpoints:
  - path: "/preferences/country/{preferenceCode}"
    method: ANY           # GET | POST | PUT | PATCH | DELETE | ANY
    acl_priority: HIGH    # HIGH | MEDIUM | LOW
    label: "Get Country Preference"
    # service_name: auth-service   # only needed for monorepos

  - path: "/api/v1/auth/login"
    method: POST
    acl_priority: HIGH
    label: "Login"
    service_name: auth-service
```

---

## Running the pipeline

```bash
# Full reset + run (default — use this for demos)
bash run.sh

# Resume from a specific phase (no reset)
bash run.sh --from 3      # skip clone + discovery, re-run analysis onwards
bash run.sh --from 4      # skip analysis, re-render docs from existing JSON

# Run only one phase
bash run.sh --only 2      # discovery only

# Re-run a single endpoint
bash run.sh --api auth-service_POST_api_v1_auth_login

# Skip reset but run everything
bash run.sh --no-reset
```

---

## Pipeline phases

### Phase 1a — Clone (`1-clone-repo.sh`)
Shallow clones the repo (`--depth=1`), copies `.claudeignore`, strips build artefacts and dependencies. Git operations stay in bash.

**Token cost:** Zero — no Claude invocations.

### Phase 1b — Discovery (`discover.py`)
One Claude invocation per service. Claude reads the codebase and returns a structured JSON list of every HTTP endpoint. The list is then filtered against `target-endpoints.yaml`.

**Token cost:** Low — one small Claude session per service.

**Supports:** Spring Boot (Java/Kotlin), FastAPI, Flask, Gin, Echo, Chi, Fiber, Express, NestJS.

### Phase 2 — Analysis (`analyze.py`)
One Claude invocation per endpoint, running in parallel (`ThreadPoolExecutor`). Claude reads the handler file and all relevant imports, then returns a full JSON analysis covering every documentation section.

**Token cost:** This is the main cost phase — one medium Claude session per endpoint.

**Features:**
- Parallel execution — all N endpoints analyzed simultaneously
- Automatic retry — up to 3 attempts if JSON is invalid or missing required fields
- Resume — already-analyzed endpoints are validated and skipped
- Validation — all 9 required fields checked before saving

### Phase 3 — Rendering (`render.py`)
Pure Python — no Claude. Converts each JSON analysis file into formatted Markdown using `ThreadPoolExecutor` for parallel rendering. Handles any malformed data gracefully using `safe_list` / `safe_str_list` helpers.

**Token cost:** Zero.

### Phase 4 — Assembly (`assemble.py`)
Pure Python — no Claude. Builds:
- `output/README.md` — master table of all APIs with blast radius summary
- `output/ACL-CHECKLIST.md` — implementation order + transform catalogue + ambiguities
- `output/api-registry.json` — machine-readable registry for tooling

**Token cost:** Zero.

---

## Token breakdown

For a typical run of 4 targeted endpoints across 1 service:

| Phase | Claude calls | Approx tokens |
|---|---|---|
| Clone | 0 | 0 |
| Discovery | 1 | ~5k |
| Analysis (×4) | 4 | ~40–80k |
| Render | 0 | 0 |
| Assembly | 0 | 0 |
| **Total** | **5** | **~45–85k** |

---

## Supported languages and frameworks

| Language | Frameworks |
|---|---|
| Java | Spring Boot (`@GetMapping`, `@PostMapping`, `@RequestMapping`, etc.) |
| Kotlin | Spring Boot (same annotations as Java) |
| Python | FastAPI (`@router.get`, `@app.post`, etc.), Flask (`@app.route`) |
| Go | Gin, Echo, Chi, Fiber, net/http |
| TypeScript / JavaScript | Express, NestJS |

---

## Output files

After a successful run:

```
output/
├── README.md            ← Master index — all APIs in a table, HIGH blast radius callout
├── ACL-CHECKLIST.md     ← Ordered by blast radius, unique transform catalogue
├── api-registry.json    ← Machine-readable registry (api_id, method, path, severity, etc.)
└── docs/
    ├── product-config_GET_preferences_preferenceCode.md
    ├── product-config_GET_preferences_country_preferenceCode.md
    └── ...
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `claude: command not found` | `npm install -g @anthropic-ai/claude-code` |
| Auth error | `claude auth login` |
| `bufsize must be an integer` | Remove `...` placeholder from `subprocess.run` call |
| `name 'svc' is not defined` | Remove `--model` flag from old subprocess call |
| Endpoints not matched | Check `target-endpoints.yaml` — paths must match router exactly (Spring regex `{id:.+}` is handled automatically) |
| Missing services in monorepo | Check `ls workspace/repos/<service>/services/` and update `repos.yaml` to match real directory names |
| Interactive Claude session | Remove `claude config set model` calls — use `--model` flag or leave `CLAUDE_MODEL` empty |
| `No such file or directory: .../POST_/api/...` | IDs contain raw slashes — apply `_slugify()` fix in `analyze.py` and `discover.py` |
| Analysis JSON missing `method` | Cached file is invalid — delete it and re-run: `bash run.sh --api <id>` |

---

## Using Doctor

### Prerequisites
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed (`npm install -g @anthropic-ai/claude-code`)
- Claude Code authenticated (`claude auth login`)
- Git access to the repository you want to document

---

### Using with Claude Code

Once installed, you can ask Claude Code to run Doctor on your behalf without touching any commands.

Open Claude Code inside the `doctor/` directory:

```bash
cd doctor
claude
```

Then simply tell Claude what you want:

> _"Document the APIs in https://github.com/my-org/my-service.git"_

> _"Generate a Postman collection for the order service"_

> _"Document only the POST endpoints in this monorepo"_

Claude reads `SKILL.md` and handles the entire workflow — cloning the repo, configuring `.env`, running the pipeline, and reporting what was generated.

---

### Resuming a partial run

```bash
bash run.sh --from 3    # resume from analysis (skip clone + discovery)
bash run.sh --from 4    # re-render docs only
bash run.sh --from 5    # regenerate Postman + diagrams only
bash run.sh --only 2    # discovery only — see all endpoints before spending tokens
bash run.sh --api <id>  # re-run a single endpoint
```