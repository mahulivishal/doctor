#!/usr/bin/env bash
echo "🧹 Resetting workspace..."
rm -rf workspace/manifests/* workspace/analysis/* workspace/repos/* \
       output/docs/* output/README.md \
       output/ACL-CHECKLIST.md output/api-registry.json
echo "✅ Ready for fresh run"
echo "✅ Repo is locally cloned already, start with STEP 2"
echo "   → bash scripts/2-discover-apis.sh"