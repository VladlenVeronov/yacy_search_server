# YACY Project Meta

Roadmap, design docs, and developer tooling for the YACY redesign of YaCy.

## Files

- **[VISION.md](VISION.md)** — original product vision (in Ukrainian)
- **[PLAN.md](PLAN.md)** — 5-phase execution plan with checkboxes
- **[AUDIT_htroot.md](AUDIT_htroot.md)** — audit of `htroot/*.html` (delete / rewrite / keep)
- **[scripts/](scripts/)** — vector indexing tooling (Supabase + pgvector + HuggingFace embeddings)
- **[.yacy_env.template](.yacy_env.template)** — env-var template (copy to `~/.yacy_env` and fill in)

## Vector indexing setup (optional)

1. Copy `.yacy_env.template` to `~/.yacy_env` and fill in real keys.
2. Run the SQL migration in your Supabase project: `scripts/setup_table.sql`.
3. Install the post-commit hook from the repo root:
   ```bash
   bash docs/yacy-project/scripts/install_hook.sh
   ```
4. Reindex the whole codebase once:
   ```bash
   python3 docs/yacy-project/scripts/reindex_vectors.py --full
   ```

## Notes

- This repo is **public**. Never commit secrets, API keys, or service URLs that identify private infrastructure. All such values live in `~/.yacy_env` (gitignored at `docs/yacy-project/.yacy_env`).
- Runtime logs (`*.log`) are gitignored.
