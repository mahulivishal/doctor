"""
run_manager.py — Manages concurrent Doctor runs for the API server.
Each run executes in a separate thread from a ThreadPoolExecutor.
Run state is tracked in-memory (sufficient for single-instance K8s pods).
"""
import asyncio
import uuid
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from enum import Enum
from typing import Dict, Optional, Any
from dataclasses import dataclass, field


class RunStatus(str, Enum):
    QUEUED    = "queued"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    CANCELLED = "cancelled"


@dataclass
class RunState:
    run_id:        str
    status:        RunStatus       = RunStatus.QUEUED
    current_phase: int             = 0
    phase_label:   str             = "Queued"
    endpoints_total: int           = 0
    endpoints_done:  int           = 0
    pr_url:         Optional[str]  = None
    error:          Optional[str]  = None
    started_at:     Optional[float] = None
    completed_at:   Optional[float] = None
    config_data:    Dict[str, Any] = field(default_factory=dict)
    cloned:         bool           = False   # True if Phase 1 ran

    def elapsed_seconds(self) -> Optional[float]:
        if self.started_at is None:
            return None
        end = self.completed_at or time.time()
        return round(end - self.started_at, 1)

    def to_dict(self) -> dict:
        return {
            "run_id":           self.run_id,
            "status":           self.status.value,
            "current_phase":    self.current_phase,
            "phase_label":      self.phase_label,
            "endpoints_total":  self.endpoints_total,
            "endpoints_done":   self.endpoints_done,
            "pr_url":           self.pr_url,
            "error":            self.error,
            "elapsed_seconds":  self.elapsed_seconds(),
            "cloned":           self.cloned,
        }


class RunManager:
    def __init__(self, max_workers: int = 10):
        self._runs:     Dict[str, RunState] = {}
        self._lock      = asyncio.Lock()
        self._executor  = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="doctor-run"
        )

    def _new_run_id(self) -> str:
        return str(uuid.uuid4())[:8]

    async def create_run(self, config_data: dict) -> str:
        run_id = self._new_run_id()
        async with self._lock:
            self._runs[run_id] = RunState(
                run_id=run_id,
                config_data=config_data,
            )
        return run_id

    async def get_run(self, run_id: str) -> Optional[RunState]:
        async with self._lock:
            return self._runs.get(run_id)

    async def list_runs(self) -> list:
        async with self._lock:
            return [r.to_dict() for r in self._runs.values()]

    async def update_run(self, run_id: str, **kwargs) -> None:
        async with self._lock:
            run = self._runs.get(run_id)
            if run:
                for k, v in kwargs.items():
                    setattr(run, k, v)

    async def delete_run(self, run_id: str) -> bool:
        async with self._lock:
            if run_id in self._runs:
                del self._runs[run_id]
                return True
        return False

    def start_run(self, run_id: str, pipeline_fn) -> None:
        """Submit pipeline_fn to the thread pool. Non-blocking."""
        loop = asyncio.get_event_loop()

        def _thread_wrapper():
            asyncio.run_coroutine_threadsafe(
                self.update_run(
                    run_id,
                    status=RunStatus.RUNNING,
                    started_at=time.time(),
                    phase_label="Starting"
                ),
                loop,
            ).result()
            try:
                pipeline_fn(run_id, loop)
                asyncio.run_coroutine_threadsafe(
                    self.update_run(
                        run_id,
                        status=RunStatus.COMPLETED,
                        completed_at=time.time(),
                        phase_label="Completed",
                    ),
                    loop,
                ).result()
            except Exception as e:
                asyncio.run_coroutine_threadsafe(
                    self.update_run(
                        run_id,
                        status=RunStatus.FAILED,
                        completed_at=time.time(),
                        phase_label="Failed",
                        error=str(e),
                    ),
                    loop,
                ).result()

        self._executor.submit(_thread_wrapper)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)


# ─── Progress callback ────────────────────────────────────────────────────────

class ProgressReporter:
    """
    Passed into pipeline.py so it can report progress back to run_manager
    without importing FastAPI / asyncio directly.
    """
    def __init__(self, run_id: str, manager: RunManager, loop):
        self.run_id  = run_id
        self.manager = manager
        self.loop    = loop

    def update(self, **kwargs) -> None:
        asyncio.run_coroutine_threadsafe(
            self.manager.update_run(self.run_id, **kwargs),
            self.loop,
        ).result()

    def set_phase(self, phase: int, label: str) -> None:
        self.update(current_phase=phase, phase_label=label)

    def set_endpoints(self, total: int) -> None:
        self.update(endpoints_total=total, endpoints_done=0)

    def increment_done(self) -> None:
        asyncio.run_coroutine_threadsafe(
            self._increment(),
            self.loop,
        ).result()

    async def _increment(self) -> None:
        async with self.manager._lock:
            run = self.manager._runs.get(self.run_id)
            if run:
                run.endpoints_done += 1
