#!/bin/bash
# YACY post-commit hook — runs after every git commit
# Installed at: yacy_search_server/.git/hooks/post-commit

SCRIPT_DIR="$(cd "$(dirname "$0")/../../../scripts" && pwd)"
PYTHON="${PYTHON:-python3}"

# Load env if exists
if [ -f "$HOME/.yacy_env" ]; then
  source "$HOME/.yacy_env"
fi

# Check required env vars
if [ -z "$SUPABASE_SERVICE_KEY" ] || [ -z "$OPENAI_API_KEY" ]; then
  echo "[yacy-vectors] Skipping: SUPABASE_SERVICE_KEY or OPENAI_API_KEY not set"
  echo "[yacy-vectors] Set them in ~/.yacy_env to enable auto-reindex"
  exit 0
fi

echo "[yacy-vectors] Reindexing changed files..."
$PYTHON "$SCRIPT_DIR/reindex_vectors.py" 2>&1 | tee -a "$SCRIPT_DIR/reindex.log"

exit 0
