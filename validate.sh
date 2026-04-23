#!/usr/bin/env bash
# =============================================================================
# validate.sh — Pre-flight checks before you spend any tokens
# Run this once after cloning the framework to verify your environment
# =============================================================================
set -euo pipefail
source .env

PASS=0
FAIL=0

check() {
  local label="$1"
  local cmd="$2"
  if eval "$cmd" &>/dev/null; then
    echo "  ✅  $label"
    ((PASS++)) || true
  else
    echo "  ❌  $label"
    ((FAIL++)) || true
  fi
}

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║         doctor  ·  Pre-flight                ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

echo "── Tools ──────────────────────────────────────"
check "Claude Code installed (claude)" "command -v claude"
check "Python 3 available"             "command -v python3"
check "git available"                  "command -v git"
check "jq available (optional)"        "command -v jq"
echo ""

echo "── Claude Code auth ───────────────────────────"
AUTH_RESULT=$(claude -p "say ok" 2>/dev/null || true)
if echo "$AUTH_RESULT" | grep -qi "ok"; then
  echo "  ✅  Claude Code authenticated"
  ((PASS++)) || true
else
  echo "  ❌  Claude Code authenticated"
  ((FAIL++)) || true
fi

echo "── Repo reachability ──────────────────────────"
check "$SERVICE repo reachable" "git ls-remote $RAW_REPO HEAD"
echo ""

echo "── Directory structure ────────────────────────"
echo "mkdir -p workspace/{repos,manifests,analysis} output/docs"
check "workspace/repos/ exists"     "[ -d workspace/repos ]"
check "workspace/manifests/ exists" "[ -d workspace/manifests ]"
check "workspace/analysis/ exists"  "[ -d workspace/analysis ]"
check "output/docs/ exists"         "[ -d output/docs ]"
check "config/repos.yaml exists"    "[ -f config/repos.yaml ]"
check "config/.claudeignore exists" "[ -f config/.claudeignore ]"
check "CLAUDE.md exists"            "[ -f CLAUDE.md ]"
echo ""

echo "── Scripts executable ─────────────────────────"
for script in scripts/*.sh; do
  check "$script" "[ -x $script ] || chmod +x $script"
done
echo ""

# Make all scripts executable automatically
chmod +x scripts/*.sh run.sh validate.sh 2>/dev/null || true

if [ "$FAIL" -eq 0 ]; then
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "✅  All checks passed ($PASS/$((PASS+FAIL)))"
  echo "   Ready to run: bash run.sh"
else
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "⚠️  $FAIL check(s) failed. Fix above before running."
  echo ""
  echo "Common fixes:"
  echo "  Claude Code not installed → npm install -g @anthropic-ai/claude-code"
  echo "  Not authenticated        → claude auth login"
  echo "  jq not installed         → brew install jq  (or apt install jq)"
  exit 1
fi
echo ""
