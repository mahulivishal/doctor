"""
clone.py — Phase 1: Clone a repo from any supported VCS provider.
Supports: GitHub, GitLab (cloud + self-hosted), Azure Repos, Bitbucket.
Replaces 1-clone-repo.sh.
"""
import os
import re
import shutil
import subprocess
from config import Config


# ─── URL Construction ─────────────────────────────────────────────────────────

def _authenticated_url(cfg: Config) -> str:
    """
    Build an authenticated clone URL for the given VCS provider.
    Token is embedded in the URL — never logged.
    """
    repo     = cfg.repo
    token    = cfg.vcs_token
    provider = cfg.vcs_provider
    base_url = cfg.vcs_base_url.rstrip("/")

    # If no token, use repo URL as-is (SSH or public HTTPS)
    if not token:
        return repo

    # Strip any existing credentials from URL
    repo = re.sub(r'https?://[^@]*@', 'https://', repo)

    if provider == "github":
        # https://<token>@github.com/org/repo.git
        return repo.replace("https://", f"https://{token}@")

    if provider == "gitlab":
        # Self-hosted GitLab or gitlab.com
        # https://oauth2:<token>@git.company.com/org/repo.git
        if base_url:
            path = re.sub(r'https?://[^/]+', '', repo)
            return f"{base_url.replace('https://', f'https://oauth2:{token}@')}{path}"
        return repo.replace("https://", f"https://oauth2:{token}@")

    if provider == "azure":
        # https://<token>@dev.azure.com/org/project/_git/repo
        return repo.replace("https://", f"https://{token}@")

    if provider == "bitbucket":
        # https://x-token-auth:<token>@bitbucket.org/org/repo.git
        return repo.replace("https://", f"https://x-token-auth:{token}@")

    # Unknown provider — try basic token injection
    return repo.replace("https://", f"https://{token}@")


def _strip_credentials(url: str) -> str:
    """Remove token from URL for safe logging."""
    return re.sub(r'(https?://)([^@]+@)', r'\1***@', url)


# ─── Clone ────────────────────────────────────────────────────────────────────

def _run_git(args: list, cwd: str = None, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args[:2])} failed:\n{result.stderr.strip()}"
        )
    return result


def run(cfg: Config) -> bool:
    """
    Clone the configured repo into cfg.repo_root.
    Returns True if cloned fresh, False if already present (skipped).
    """
    target = cfg.repo_root

    print(f"━" * 50)
    print(f" Phase 1: Clone — {cfg.service}")
    print(f" Provider: {cfg.vcs_provider}")
    print(f" Repo:     {_strip_credentials(cfg.repo)}")
    print(f" Branch:   {cfg.branch}")
    print(f"━" * 50)

    # ── Already cloned ─────────────────────────────────────────────────────
    if os.path.isdir(os.path.join(target, ".git")):
        print(f"⏭  Already cloned at {target} — skipping")
        return False

    # ── Verify reachability ────────────────────────────────────────────────
    print("🔗 Checking repo access...")
    auth_url = _authenticated_url(cfg)
    result = subprocess.run(
        ["git", "ls-remote", auth_url, "HEAD"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Cannot reach repo: {_strip_credentials(cfg.repo)}\n"
            f"Check your VCS_PROVIDER, token, and VCS_BASE_URL.\n"
            f"Error: {result.stderr.strip()}"
        )
    print("✓  Repo reachable")

    # ── Clone ──────────────────────────────────────────────────────────────
    print(f"📥 Cloning (shallow, depth=1)...")
    os.makedirs(target, exist_ok=True)

    try:
        _run_git([
            "clone", "--depth=1", "--branch", cfg.branch,
            auth_url, target
        ])
    except RuntimeError:
        # Try default branch if specified branch not found
        print(f"⚠️  Branch '{cfg.branch}' not found, trying default branch...")
        _run_git(["clone", "--depth=1", auth_url, target])

    print("✓  Clone complete")

    # ── Drop .claudeignore ────────────────────────────────────────────────
    claudeignore_src = os.path.join(cfg.project_root, "config", ".claudeignore")
    if os.path.exists(claudeignore_src):
        shutil.copy(claudeignore_src, os.path.join(target, ".claudeignore"))

    # ── Strip noise ────────────────────────────────────────────────────────
    print("🧹 Stripping noise directories...")
    noise = ["node_modules", ".git", "dist", "build", "__pycache__",
             "target", ".gradle", "venv", ".venv", "coverage"]
    for d in noise:
        noise_path = os.path.join(target, d)
        if os.path.isdir(noise_path):
            shutil.rmtree(noise_path)

    # ── Summary ───────────────────────────────────────────────────────────
    total_files  = sum(len(files) for _, _, files in os.walk(target))
    src_exts     = {".java", ".kt", ".py", ".go", ".ts", ".js", ".cs", ".rb", ".php"}
    source_files = sum(
        1 for _, _, files in os.walk(target)
        for f in files if os.path.splitext(f)[1] in src_exts
    )
    print(f"\n📊 Repo ready: {total_files} total files, {source_files} source files")
    print(f"   Location: {target}")

    return True  # cloned fresh


# ─── Branch + commit for PR ───────────────────────────────────────────────────

def create_pr_branch(cfg: Config, branch_name: str) -> None:
    """Create and push a new branch with the generated output."""
    repo_path = cfg.repo_root

    print(f"\n🌿 Creating branch: {branch_name}")

    # Configure git identity for the commit
    _run_git(["config", "user.email", "doctor@noreply.local"], cwd=repo_path)
    _run_git(["config", "user.name",  "Doctor Bot"],           cwd=repo_path)

    # Create branch
    _run_git(["checkout", "-b", branch_name], cwd=repo_path)

    # Copy output into repo under docs/doctor/<service>/
    dest = os.path.join(repo_path, "docs", "doctor", cfg.service)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(cfg.output_dir, dest)
    print(f"   Copied output → docs/doctor/{cfg.service}/")

    # Stage and commit
    _run_git(["add", "-A"], cwd=repo_path)
    commit_msg = (
        f"Doctor: API docs for {cfg.service} "
        f"[run {cfg.run_id}]"
    )
    _run_git(["commit", "-m", commit_msg], cwd=repo_path)

    # Push — use authenticated URL
    auth_url = _authenticated_url(cfg)
    _run_git(["push", auth_url, branch_name], cwd=repo_path)

    print(f"✓  Branch pushed: {branch_name}")
