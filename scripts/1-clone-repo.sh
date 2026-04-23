#!/usr/bin/env bash
# =============================================================================
# PHASE 1a — Clone repo
# =============================================================================
set -euo pipefail
source "$(dirname "$0")/../.env"

export SERVICE
export REPO
export CLAUDE_MODEL
export PARALLEL_WORKERS
export IS_MONOREPO

TARGET="workspace/repos/$SERVICE"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Phase 1a: Cloning — $SERVICE"
echo " Monorepo: ${IS_MONOREPO:-false}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "🔗 Checking repo access..."
if ! git ls-remote "$REPO" HEAD &>/dev/null; then
  echo "❌ Cannot reach repo. Check VPN / credentials."
  exit 1
fi
echo "✓  Repo reachable"

if [ -d "$TARGET/.git" ]; then
  echo "⏭  Already cloned — skipping"
else
  echo "📥 Cloning (shallow, depth=1)..."
  git clone --depth=1 --branch "$BRANCH" "$REPO" "$TARGET" \
  || git clone --depth=1 --branch master "$REPO" "$TARGET"
  echo "✓  Clone complete"
fi

# Drop .claudeignore
cp config/.claudeignore "$TARGET/.claudeignore"

# Strip noise
echo "🧹 Stripping noise..."
for dir in node_modules .git dist build coverage __pycache__ .venv venv target .gradle; do
  find "$TARGET" -type d -name "$dir" -exec rm -rf {} + 2>/dev/null || true
done

# Summary
echo ""
echo "📊 Token footprint:"
find "$TARGET" -type f | wc -l | xargs echo "   Total files:"
find "$TARGET" -type f \( \
  -name "*.java" -o -name "*.kt" -o -name "*.py" -o \
  -name "*.go"   -o -name "*.ts" -o -name "*.js" \
\) | wc -l | xargs echo "   Source files:"

if [ "${IS_MONOREPO:-false}" = "true" ]; then
  echo ""
  echo "📁 Top-level service directories:"
  python3 -c "
import re
with open('config/repos.yaml') as f: content = f.read()
paths = re.findall(r'path:\s*(\S+)', content)
for p in paths: print(f'   {p}')
" 2>/dev/null || echo "   (parse repos.yaml to see services)"
fi

echo ""
echo "✅ Phase 1a complete → $TARGET"
echo "   → Next: bash scripts/2-discover-apis.sh"