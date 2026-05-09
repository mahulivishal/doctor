"""
config.py — Loads and validates all configuration.
"""
import os
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Set
import shutil


@dataclass
class ServiceConfig:
    name: str
    path: str
    api_paths: List[str] = field(default_factory=lambda: ["."])


@dataclass
class TargetEndpoint:
    path: str
    method: str = "ANY"
    label: str = ""
    acl_priority: str = "HIGH"
    service_name: Optional[str] = None


# Valid skip keys — map to artifact/phase names
SKIP_OPTIONS = {
    "docs":      "Skip markdown API docs (documents/)",
    "datamodel": "Skip Mermaid class diagrams (data_model/)",
    "er":        "Skip ER diagrams (db_entity_relations/)",
    "postman":   "Skip Postman collections (postman_collection/)",
    "swagger":   "Skip OpenAPI YAML (api_document/)",
}


@dataclass
class Config:
    # Repo
    service: str
    repo: str
    branch: str
    repo_root: str

    # Monorepo
    is_monorepo: bool
    services: List[ServiceConfig]

    # Claude / Anthropic
    api_key: str           # ANTHROPIC_API_KEY
    claude_bin: str
    claude_model: str
    parallel_workers: int

    # What to skip
    skip: Set[str]         # subset of SKIP_OPTIONS keys

    # Endpoints
    target_endpoints: List[TargetEndpoint]

    # Workspace paths
    project_root: str
    analysis_dir: str
    manifests_dir: str

    # Output paths
    output_dir: str
    docs_dir: str
    data_model_dir: str
    db_er_dir: str
    postman_dir: str
    api_doc_dir: str


def _strip_comments(content: str) -> str:
    return '\n'.join(
        line for line in content.splitlines()
        if not line.strip().startswith('#')
    )


def _parse_list(content: str, key: str) -> List[str]:
    pattern = rf'{re.escape(key)}:\s*\n((?:\s+-[^\n]+\n?)*)'
    match = re.search(pattern, content)
    if not match:
        return []
    return [re.sub(r'^\s*-\s*', '', l).strip()
            for l in match.group(1).splitlines()
            if l.strip().startswith('-')]


def _find_claude() -> str:
    found = shutil.which("claude")
    if found:
        return found
    for c in [
        os.path.expanduser("~/.local/bin/claude"),
        "/usr/local/bin/claude",
        "/opt/homebrew/bin/claude",
    ]:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return "claude"  # fall back and let subprocess handle the error


def load(project_root: str = ".", skip: Optional[Set[str]] = None) -> Config:
    project_root = str(Path(project_root).resolve())
    skip = skip or set()

    # ── .env ──────────────────────────────────────────────────────────────
    env = {}
    with open(os.path.join(project_root, ".env")) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                env[k.strip()] = v.strip()

    service  = env.get("SERVICE", "")
    repo     = env.get("REPO", "")
    branch   = env.get("BRANCH", "main")
    is_mono  = env.get("IS_MONOREPO", "false").lower() == "true"
    model    = env.get("CLAUDE_MODEL", "claude-sonnet-4-5")
    workers  = int(env.get("PARALLEL_WORKERS", "4"))
    api_key  = env.get("ANTHROPIC_API_KEY", "") or os.environ.get("ANTHROPIC_API_KEY", "")

    if not service:
        raise ValueError("SERVICE not set in .env")
    if not repo:
        raise ValueError("REPO not set in .env")
    if not api_key:
        print("ℹ️  ANTHROPIC_API_KEY not set — token tracking disabled")
        print("   To enable: add ANTHROPIC_API_KEY=sk-ant-... to .env")

    repo_root = os.path.join(project_root, "workspace", "repos", service)

    # ── repos.yaml ────────────────────────────────────────────────────────
    repos_yaml = os.path.join(project_root, "config", "repos.yaml")
    services: List[ServiceConfig] = []

    if os.path.exists(repos_yaml):
        with open(repos_yaml) as f:
            content = _strip_comments(f.read())

        if is_mono:
            name_matches = re.findall(r'- name:\s*(\S+)', content)
            path_matches = re.findall(r'  path:\s*(\S+)', content)
            if not name_matches:
                raise ValueError(
                    "IS_MONOREPO=true but no services defined in config/repos.yaml.\n"
                    "Add a services block:\n\n"
                    "  repo:\n"
                    "    services:\n"
                    "      - name: auth-service\n"
                    "        path: services/auth-service\n"
                )
            for i, name in enumerate(name_matches):
                svc_path = os.path.join(repo_root, path_matches[i]) \
                           if i < len(path_matches) else repo_root
                services.append(ServiceConfig(name=name, path=svc_path))
        else:
            api_paths = _parse_list(content, "api_paths") or ["."]
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
            content = _strip_comments(f.read())
        paths     = re.findall(r'path:\s*"([^"]+)"', content)
        methods   = re.findall(r'method:\s*(\S+)',    content)
        labels    = re.findall(r'label:\s*"([^"]+)"', content)
        prios     = re.findall(r'acl_priority:\s*(\S+)', content)
        svc_names = re.findall(r'service_name:\s*(\S+)', content)

        for i, path in enumerate(paths):
            target_endpoints.append(TargetEndpoint(
                path=path,
                method=methods[i]      if i < len(methods)    else "ANY",
                label=labels[i]        if i < len(labels)     else "",
                acl_priority=prios[i]  if i < len(prios)      else "HIGH",
                service_name=svc_names[i] if i < len(svc_names) else None,
            ))

    # ── Output directories ─────────────────────────────────────────────────
    output_dir     = os.path.join(project_root, "output")
    docs_dir       = os.path.join(output_dir, "documents")
    data_model_dir = os.path.join(output_dir, "data_model")
    db_er_dir      = os.path.join(output_dir, "db_entity_relations")
    postman_dir    = os.path.join(output_dir, "postman_collection")
    api_doc_dir    = os.path.join(output_dir, "api_document")
    analysis_dir   = os.path.join(project_root, "workspace", "analysis")
    manifests_dir  = os.path.join(project_root, "workspace", "manifests")

    for d in [analysis_dir, manifests_dir, output_dir,
              docs_dir, data_model_dir, db_er_dir, postman_dir, api_doc_dir]:
        os.makedirs(d, exist_ok=True)

    claude_bin = _find_claude()
    
    return Config(
        service=service, repo=repo, branch=branch, repo_root=repo_root,
        is_monorepo=is_mono, services=services,
        api_key=api_key, claude_model=model, parallel_workers=workers,
        skip=skip, target_endpoints=target_endpoints, claude_bin=claude_bin,
        project_root=project_root,
        analysis_dir=analysis_dir, manifests_dir=manifests_dir,
        output_dir=output_dir, docs_dir=docs_dir,
        data_model_dir=data_model_dir, db_er_dir=db_er_dir,
        postman_dir=postman_dir, api_doc_dir=api_doc_dir,
    )