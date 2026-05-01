# VIR GOO — open, decentralized search

> A fork of **YaCy** that strips away SEO bias, embraces semantic search, and
> respects privacy by default. No tracking, no algorithmic dark patterns, no
> ads. Run your own node, or use a public instance.

**Live demo:** [https://search.newsgroup.site](https://search.newsgroup.site)

---

## What's different from upstream YaCy / from Google

| | VIR GOO | upstream YaCy | Google |
|---|---|---|---|
| **Ranking** | semantic embeddings (`intfloat/multilingual-e5`) + freshness + domain quality | TF-IDF + backlinks + freshness | PageRank + ML black box + ads |
| **Backlink/PageRank boost** | ❌ disabled (Google-style spam advantage gone) | ✅ enabled | core signal |
| **Third-party fetches** | ❌ none — Tailwind, fonts, icons all local | partial (Vimeo, OSM, etc.) | extensive |
| **Data ownership** | self-hosted, P2P-shareable | self-hosted, P2P-shareable | corporate |
| **Crawler queue** | priority-aware, AI-gap-filled | manual | proprietary |
| **User accounts** | optional, OIDC (Authentik) | none | mandatory tracking |
| **API for integrations** | public REST + OIDC + webhooks | partial | paid + rate-limited |
| **Source available** | ✅ (this repo) | ✅ | ❌ |

## Architecture

```
              ┌─────────────────────────────────────┐
              │  search.newsgroup.site (Traefik)    │
              └─────────┬─────────────┬─────────────┘
                        │             │
        ┌───────────────▼───┐  ┌─────▼──────────────────┐
        │  yacy (Java)      │  │  vector_service        │
        │  - public UI      │  │  (FastAPI, port 8001)  │
        │  - admin pages    │  │  - /rank (60/25/15)    │
        │  - Solr index     │  │  - /search semantic    │
        │  - crawler        │  │  - /admin/*  CRUD      │
        │  - P2P (YaCy)     │  │  - /cabinet/* OIDC     │
        └─────────┬─────────┘  └─────┬──────────────────┘
                  │ Solr             │
                  └─────────┐  ┌─────┘
                            │  │
                  ┌─────────▼──▼────────┐
                  │  pgvector (768d)    │
                  │  + analytics tables │
                  └─────────────────────┘

                  ┌─────────────────────────────────────┐
                  │  auth.vir.group (Authentik OIDC)    │
                  │  — user cabinet auth                │
                  └─────────────────────────────────────┘
```

## Key features

- **Semantic search** via `intfloat/multilingual-e5-base` — works cross-lingual
  (UA query → EN docs and vice versa).
- **No Google-style PageRank** — `coeff_authority` = 0, `coeff_citation` = 0.
- **Content blacklist** is preserved and sharper (~400 entries: porn, casino,
  state-affiliated outlets, mainstream social).
- **AI gap-analyzer** — zero-click queries → LLM (DeepSeek/OpenAI-compat) →
  seed URLs → autocrawl. Daily cron heals the index.
- **User cabinet** with saved searches, bookmarks and subscriptions
  (worker scans hourly).
- **Webmaster cabinet** — public form for site submissions, admin queue
  with priority (`high/normal/low`).
- **Auto-deploy** — `git push` → ≤5 min in production.

## Deploy your own

See [`deploy/README.md`](deploy/README.md). 5-minute install on any
Ubuntu/Debian box with Docker:

```bash
git clone -b feature/remove-third-party-links \
    https://github.com/VladlenVeronov/yacy_search_server.git yacy-fork
cp yacy-fork/deploy/docker-compose.yml ./
cp yacy-fork/deploy/.env.example ./.env
nano .env    # fill YACY_HOST, POSTGRES_PASSWORD, ADMIN_TOKEN
docker compose up -d
```

LLM API keys (DeepSeek/OpenAI) and OIDC credentials go into the same `.env`
— never committed. See `deploy/.env.example` for the full template.

## Origin / credits

Forked from [`yacy/yacy_search_server`](https://github.com/yacy/yacy_search_server).
The Java core, P2P protocol, Solr integration and crawler are upstream YaCy.
The `vector_service/`, the new `htroot/cabinet.html` / `submit-site.html` /
`admin-services.html`, the Tailwind public UI, the OIDC integration and
the `deploy/` reference are VIR GOO additions.

## License

GPL-2.0 (same as upstream YaCy).
