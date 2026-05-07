#!/usr/bin/env bash
echo "🧹 Resetting workspace..."
rm -rf workspace/* \
       output/* \
       output/README.md \
       output/ACL-CHECKLIST.md output/api-registry.json
echo "✅ Ready for fresh run"
echo "✅ If the Repo is locally cloned already move it to workspace/repos/ and start with STEP 2"
echo "   → bash scripts/2-discover-apis.sh"