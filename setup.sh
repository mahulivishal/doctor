#!/usr/bin/env bash
# =============================================================================
# setup.sh — One-time workbench setup
# Run this once after cloning the framework before anything else
# =============================================================================
set -euo pipefail

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║        doctor  ·  Setup                      ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# --- Directories ---
echo "📁 Creating workspace directories..."
mkdir -p workspace/repos
mkdir -p workspace/manifests
mkdir -p workspace/analysis
mkdir -p output/documents
mkdir -p output/data_model
mkdir -p output/db_entity_relations
mkdir -p output/postman_collection
mkdir -p output/api_document

echo "   ✅  workspace/repos/"
echo "   ✅  workspace/manifests/"
echo "   ✅  workspace/analysis/"
echo "   ✅  output/documents/"
echo "   ✅  output/data_model/"
echo "   ✅  output/db_entity_relations/"
echo "   ✅  output/postman_collection/"
echo "   ✅  output/api_document/"

# --- .gitignore ---
echo ""
echo "📋 Writing .gitignore..."
cat > .gitignore << 'EOF'
.env
workspace/
output/
EOF
echo "   ✅  .gitignore"

# --- Scripts executable ---
echo ""
echo "🔑 Making scripts executable..."
chmod +x scripts/*.sh run.sh validate.sh setup.sh
echo "   ✅  All scripts"

# --- .env check ---
echo ""
if [ ! -f ".env" ]; then
  echo "⚠️  No .env file found. Creating template..."
  cat > .env.template << 'EOF'
# Service
SERVICE=product-config
BRANCH=main
REPO=https://your-username:your-token@git.build.ingka.ikea.com/selling-api/product-config.git
EOF
  echo "   ✅  .env.template created — copy it to .env and fill in your values:"
  echo "       cp .env.template .env"
else
  echo "   ✅  .env found"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅  Setup complete."
echo ""
echo "   Next steps:"
echo "   1. Fill in .env (if not already done)"
echo "   2. claude auth login"
echo "   3. bash validate.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""