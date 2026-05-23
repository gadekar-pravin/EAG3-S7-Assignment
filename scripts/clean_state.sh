#!/usr/bin/env bash
set -euo pipefail

# Remove durable agent state but preserve sandbox fixtures (papers/).
rm -rf state usage.json

# Remove agent-generated files in sandbox/ but keep papers/.
if [ -d sandbox ]; then
    find sandbox -maxdepth 1 -type f -delete
fi

echo "Cleaned state/, usage.json, and generated sandbox files."
echo "Preserved: sandbox/papers/"
