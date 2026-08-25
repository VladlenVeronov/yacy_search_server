#!/bin/bash
# Install post-commit git hook for YACY vector reindexing
# Run from yacy_search_server repo root: bash docs/yacy-project/scripts/install_hook.sh

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
HOOK_DIR="$REPO_ROOT/.git/hooks"
HOOK_FILE="$HOOK_DIR/post-commit"

if [ ! -d "$HOOK_DIR" ]; then
  echo "ERROR: Not a git repo at $REPO_ROOT"
  exit 1
fi

# Write hook (paths relative to .git/hooks/)
cat > "$HOOK_FILE" << 'HOOK'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")/../../docs/yacy-project/scripts" && pwd)"
PYTHON="${PYTHON:-python3}"
if [ -f "$HOME/.yacy_env" ]; then source "$HOME/.yacy_env"; fi
if [ -z "$SUPABASE_SERVICE_KEY" ] || [ -z "$OPENAI_API_KEY" ]; then
  echo "[yacy-vectors] Skipping: env vars not set (add to ~/.yacy_env)"
  exit 0
fi
echo "[yacy-vectors] Reindexing changed files..."
$PYTHON "$SCRIPT_DIR/reindex_vectors.py" >> "$SCRIPT_DIR/reindex.log" 2>&1 &
echo "[yacy-vectors] Reindex started in background (pid $!)"
exit 0
HOOK

chmod +x "$HOOK_FILE"
echo "Hook installed: $HOOK_FILE"

# Create env template in $HOME if not exists (placeholder values only)
if [ ! -f "$HOME/.yacy_env" ]; then
  cat > "$HOME/.yacy_env" << 'ENV'
export SUPABASE_URL="https://your-project-ref.supabase.co"
export SUPABASE_SERVICE_KEY="your-service-key-here"
export OPENAI_API_KEY="your-openai-key-here"
ENV
  echo "Created ~/.yacy_env — fill in your keys"
fi

echo ""
echo "Setup complete!"
echo "  1. Edit ~/.yacy_env with your Supabase + OpenAI keys"
echo "  2. Run SQL migration: docs/yacy-project/scripts/setup_table.sql in Supabase dashboard"
echo "  3. Run full index once: python3 docs/yacy-project/scripts/reindex_vectors.py --full"
echo "  4. After every git commit — hook runs automatically (background)"
