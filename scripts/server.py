"""
server.py — Doctor HTTP API server.
Each POST /run starts a pipeline in a background thread.
Authentication: X-Doctor-Key header.

Start:
  uvicorn scripts.server:app --host 0.0.0.0 --port 8000
"""
import asyncio
import io
import os
import sys
import zipfile
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(__file__))

import config as cfg_module
from run_manager import RunManager, RunStatus, ProgressReporter

# ─── Global run manager ───────────────────────────────────────────────────────

manager = RunManager(max_workers=int(os.environ.get("MAX_CONCURRENT_RUNS", "10")))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    manager.shutdown()


app = FastAPI(
    title="Doctor API",
    description="DOCument creaTOR — API documentation generation as a service",
    version="1.0.0",
    lifespan=lifespan,
)


# ─── Auth ─────────────────────────────────────────────────────────────────────

DOCTOR_API_KEY = os.environ.get("DOCTOR_API_KEY", "")


async def require_api_key(x_doctor_key: str = Header(...)):
    if not DOCTOR_API_KEY:
        return  # No key configured — open access (dev mode)
    if x_doctor_key != DOCTOR_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ─── Request / Response models ────────────────────────────────────────────────

class ServiceDef(BaseModel):
    name: str
    path: str
    api_paths: List[str] = ["."]


class TargetEndpointDef(BaseModel):
    path: str
    method: str = "ANY"
    label: str = ""
    acl_priority: str = "HIGH"
    service_name: Optional[str] = None


class RunRequest(BaseModel):
    # Repo
    service: str
    repo: str
    branch: str = "main"

    # VCS
    vcs_provider: str = "github"        # github | gitlab | azure | bitbucket
    vcs_token: str = ""
    vcs_base_url: str = ""              # for self-hosted GitLab/Azure

    # Monorepo
    is_monorepo: bool = False
    services: List[ServiceDef] = []

    # Claude
    anthropic_api_key: str = ""
    claude_model: str = ""
    parallel_workers: int = 4

    # Endpoints
    target_endpoints: List[TargetEndpointDef] = []

    # Skip artifacts
    skip: List[str] = []

    # PR
    raise_pr: bool = False
    pr_base_branch: str = ""

    class Config:
        json_schema_extra = {
            "example": {
                "service":        "my-service",
                "repo":           "https://github.com/org/my-service.git",
                "branch":         "main",
                "vcs_provider":   "github",
                "vcs_token":      "ghp_...",
                "parallel_workers": 4,
                "target_endpoints": [
                    {"path": "/api/v1/orders", "method": "POST", "label": "Create Order"}
                ],
                "raise_pr": True,
            }
        }


# ─── Pipeline runner (runs in thread) ────────────────────────────────────────

def _run_pipeline(run_id: str, config_data: dict, loop) -> None:
    """Called in a background thread. Imports pipeline here to avoid circular deps."""
    import pipeline as pl
    import clone
    import pr as pr_module
    import asyncio as _asyncio

    reporter = ProgressReporter(run_id, manager, loop)

    try:
        cfg = cfg_module.load_from_dict(config_data, PROJECT_ROOT, run_id)

        reporter.set_phase(1, "Cloning repository")
        cloned = clone.run(cfg)

        _asyncio.run_coroutine_threadsafe(
            manager.update_run(run_id, cloned=cloned),
            loop,
        ).result()

        reporter.set_phase(2, "Discovering endpoints")
        endpoints = pl.run_discover(cfg)

        reporter.set_phase(3, "Analyzing endpoints")
        reporter.set_endpoints(len(endpoints))
        pl.run_analyze(cfg, endpoints, reporter=reporter)

        if "docs" not in cfg.skip:
            reporter.set_phase(4, "Rendering documentation")
            pl.run_render(cfg)

        reporter.set_phase(5, "Generating artifacts")
        pl.run_artifacts(cfg)

        # PR
        if cfg.raise_pr and cloned:
            reporter.set_phase(6, "Raising PR")
            from datetime import datetime
            branch_name = f"doctor/{cfg.service}-{datetime.utcnow().strftime('%Y%m%d')}-{run_id}"
            clone.create_pr_branch(cfg, branch_name)
            pr_url = _asyncio.run_coroutine_threadsafe(
                pr_module.raise_pr(cfg, branch_name, endpoints),
                loop,
            ).result()
            _asyncio.run_coroutine_threadsafe(
                manager.update_run(run_id, pr_url=pr_url),
                loop,
            ).result()
        elif cfg.raise_pr and not cloned:
            print(f"⏭  PR skipped — repo was not cloned in this run")

    except Exception as e:
        raise


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "doctor"}


@app.post("/run", status_code=202, dependencies=[Depends(require_api_key)])
async def start_run(request: RunRequest):
    """Start a Doctor documentation run. Returns immediately with run_id."""
    config_data = request.dict()
    run_id = await manager.create_run(config_data)
    loop   = asyncio.get_event_loop()

    manager.start_run(
        run_id,
        lambda rid, lp: _run_pipeline(rid, config_data, lp)
    )

    return {
        "run_id": run_id,
        "status": "queued",
        "poll":   f"/run/{run_id}",
    }


@app.get("/run/{run_id}", dependencies=[Depends(require_api_key)])
async def get_run_status(run_id: str):
    """Poll run status and progress."""
    run = await manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return run.to_dict()


@app.get("/run/{run_id}/output", dependencies=[Depends(require_api_key)])
async def download_output(run_id: str):
    """Download generated output as a zip file."""
    run = await manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    if run.status != RunStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"Run is {run.status.value} — output only available after completion"
        )

    # Find output dir from run config
    cfg = cfg_module.load_from_dict(run.config_data, PROJECT_ROOT, run_id)
    output_dir = cfg.output_dir

    if not os.path.isdir(output_dir):
        raise HTTPException(status_code=404, detail="Output directory not found")

    # Stream as zip
    def _zip_stream():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(output_dir):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    arcname = os.path.relpath(fpath, output_dir)
                    zf.write(fpath, arcname)
        buf.seek(0)
        yield from iter(lambda: buf.read(65536), b"")

    return StreamingResponse(
        _zip_stream(),
        media_type="application/zip",
        headers={
            "Content-Disposition":
                f'attachment; filename="doctor-{run.config_data.get("service","output")}-{run_id}.zip"'
        }
    )


@app.post("/run/{run_id}/pr", dependencies=[Depends(require_api_key)])
async def raise_pr_for_run(run_id: str):
    """Manually trigger PR creation for a completed run."""
    import clone
    import pr as pr_module
    from datetime import datetime

    run = await manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    if run.status != RunStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Run must be completed before raising PR")
    if not run.cloned:
        raise HTTPException(status_code=409, detail="PR not available — repo was not cloned in this run")

    cfg = cfg_module.load_from_dict(run.config_data, PROJECT_ROOT, run_id)
    branch_name = f"doctor/{cfg.service}-{datetime.utcnow().strftime('%Y%m%d')}-{run_id}"

    try:
        clone.create_pr_branch(cfg, branch_name)
        pr_url = await pr_module.raise_pr(cfg, branch_name, [])
        await manager.update_run(run_id, pr_url=pr_url)
        return {"pr_url": pr_url, "branch": branch_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/run/{run_id}", dependencies=[Depends(require_api_key)])
async def delete_run(run_id: str):
    """Delete a run's state (does not delete generated files)."""
    deleted = await manager.delete_run(run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return {"deleted": run_id}


@app.get("/runs", dependencies=[Depends(require_api_key)])
async def list_runs():
    """List all tracked runs."""
    return await manager.list_runs()
