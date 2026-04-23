"""
config.py — Loads and validates all configuration from .env, repos.yaml,
and target-endpoints.yaml. Single source of truth for the entire pipeline.
"""
import os
import re
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ServiceConfig:
    name: str
    path: str          # absolute or relative path to the service root
    api_paths: List[str] = field(default_factory=lambda: ["."])


@dataclass
class TargetEndpoint:
    path: str
    method: str = "ANY"
    label: str = ""
    acl_priority: str = "HIGH"
    service_name: Optional[str] = None


@dataclass
class Config:
    # Repo
    service: str
    repo: str
    branch: str
    repo_root: str      # workspace/repos/<service>

    # Monorepo
    is_monorepo: bool
    services: List[ServiceConfig]

    # Claude
    claude_bin: str
    claude_model: str
    parallel_workers: int

    # Endpoints
    target_endpoints: List[TargetEndpoint]

    # Paths
    project_root: str
    analysis_dir: str
    manifests_dir: str
    output_dir: str
    docs_dir: str


def _find_claude() -> str:
    """Find claude binary — checks PATH and common install locations."""
    import shutil
    found = shutil.which("claude")
    if found:
        return found
    candidates = [
        os.path.expanduser("~/.local/bin/claude"),
        "/usr/local/bin/claude",
        "/opt/homebrew/bin/claude",
    ]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    raise RuntimeError(
        "claude binary not found. Install: npm install -g @anthropic-ai/claude-code"
    )


def _parse_yaml_simple(content: str, key: str) -> List[str]:
    """Minimal YAML list parser — no external dependency."""
    pattern = rf'{re.escape(key)}:\s*\n((?:\s+-[^\n]+\n?)*)'
    match = re.search(pattern, content)
    if not match:
        return []
    return [re.sub(r'^\s*-\s*', '', line).strip()
            for line in match.group(1).splitlines()
            if line.strip().startswith('-')]


def load(project_root: str = ".") -> Config:
    project_root = str(Path(project_root).resolve())

    # ── .env ──────────────────────────────────────────────────────────────
    env_path = os.path.join(project_root, ".env")
    env = {}
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                env[k.strip()] = v.strip()

    service  = env.get("SERVICE", "")
    repo     = env.get("REPO", "")
    branch   = env.get("BRANCH", "main")
    is_mono  = env.get("IS_MONOREPO", "false").lower() == "true"
    model = env.get("CLAUDE_MODEL", "")
    workers  = int(env.get("PARALLEL_WORKERS", "4"))

    if not service:
        raise ValueError("SERVICE not set in .env")
    if not repo:
        raise ValueError("REPO not set in .env")

    repo_root = os.path.join(project_root, "workspace", "repos", service)

    # ── repos.yaml ────────────────────────────────────────────────────────
    repos_yaml = os.path.join(project_root, "config", "repos.yaml")
    services: List[ServiceConfig] = []

    if os.path.exists(repos_yaml):
        with open(repos_yaml) as f:
            content = f.read()

        if is_mono:
            # Parse monorepo services
            name_matches  = re.findall(r'- name:\s*(\S+)', content)
            path_matches  = re.findall(r'  path:\s*(\S+)', content)

            if not name_matches:
                raise ValueError(
                    "IS_MONOREPO=true but no services defined in config/repos.yaml.\n"
                    "Add a services block with name and path for each service:\n\n"
                    "  repo:\n"
                    "    services:\n"
                    "      - name: auth-service\n"
                    "        path: services/auth-service\n"
                    "      - name: order-service\n"
                    "        path: services/order-service\n"
                )

            for i, name in enumerate(name_matches):
                svc_path = os.path.join(repo_root, path_matches[i]) \
                           if i < len(path_matches) else repo_root
                api_paths = ["."]
                services.append(ServiceConfig(
                    name=name, path=svc_path, api_paths=api_paths
                ))
        else:
            # Single service — read api_paths
            api_paths = _parse_yaml_simple(content, "api_paths") or ["."]
            services.append(ServiceConfig(
                name=service, path=repo_root, api_paths=api_paths
            ))
    else:
        services.append(ServiceConfig(name=service, path=repo_root))

    # ── target-endpoints.yaml ──────────────────────────────────────────────
    targets_yaml = os.path.join(project_root, "config", "target-endpoints.yaml")
    target_endpoints: List[TargetEndpoint] = []

    if os.path.exists(targets_yaml):
        with open(targets_yaml) as f:
            content = f.read()

        paths    = re.findall(r'path:\s*"([^"]+)"', content)
        methods  = re.findall(r'method:\s*(\S+)', content)
        labels   = re.findall(r'label:\s*"([^"]+)"', content)
        prios    = re.findall(r'acl_priority:\s*(\S+)', content)
        svc_names = re.findall(r'service_name:\s*(\S+)', content)

        for i, path in enumerate(paths):
            target_endpoints.append(TargetEndpoint(
                path=path,
                method=methods[i]    if i < len(methods)    else "ANY",
                label=labels[i]      if i < len(labels)     else "",
                acl_priority=prios[i] if i < len(prios)     else "HIGH",
                service_name=svc_names[i] if i < len(svc_names) else None,
            ))

    # ── Directories ───────────────────────────────────────────────────────
    analysis_dir  = os.path.join(project_root, "workspace", "analysis")
    manifests_dir = os.path.join(project_root, "workspace", "manifests")
    output_dir    = os.path.join(project_root, "output")
    docs_dir      = os.path.join(project_root, "output", "docs")

    for d in [analysis_dir, manifests_dir, output_dir, docs_dir]:
        os.makedirs(d, exist_ok=True)

    return Config(
        service=service,
        repo=repo,
        branch=branch,
        repo_root=repo_root,
        is_monorepo=is_mono,
        services=services,
        claude_bin=_find_claude(),
        claude_model=model,
        parallel_workers=workers,
        target_endpoints=target_endpoints,
        project_root=project_root,
        analysis_dir=analysis_dir,
        manifests_dir=manifests_dir,
        output_dir=output_dir,
        docs_dir=docs_dir,
    )
