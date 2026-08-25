# VIR GOO — open, decentralized search

> A fork of **YaCy** that strips away SEO bias, embraces semantic search,
> and respects privacy by default. No tracking, no algorithmic dark
> patterns, no ads. Run your own node, or use the public instance.

**Live demo:** [https://search.newsgroup.site](https://search.newsgroup.site)
**Repo:** [github.com/VladlenVeronov/yacy_search_server](https://github.com/VladlenVeronov/yacy_search_server) · branch `feature/remove-third-party-links`

---

## What's different from upstream YaCy / from Google

| | VIR GOO | upstream YaCy | Google |
|---|---|---|---|
| **Ranking** | semantic embeddings + freshness + domain quality | TF-IDF + backlinks + freshness | PageRank + ML black box + ads |
| **Backlink/PageRank boost** | ❌ disabled (`coeff_authority` = 0, `coeff_citation` = 0) | ✅ enabled | core signal |
| **Third-party fetches at runtime** | ❌ none — Tailwind, fonts, icons all local | partial (Vimeo, OSM, ICQ, etc. — removed in this fork) | extensive |
| **Outbound DHT share filter** | blacklist applied before transmit (porn/casino/spam never shipped) | none — relies only on inbound block | n/a |
| **Webmaster onboarding** | self-signup at `/Register.html?webmaster=1`; bot validator runs in-process Java | none | gate-kept by Search Console |
| **AI gap-fill of the index** | zero-click queries → LLM (BYO key) → seed crawls → daily cron | none | proprietary |
| **Source available** | ✅ (this repo, GPL-2.0) | ✅ | ❌ |

---

## Architecture

```
                  ┌─────────────────────────────────────┐
                  │  search.newsgroup.site (Traefik)    │
                  └─────────┬─────────────┬─────────────┘
                            │             │
            ┌───────────────▼───┐  ┌──────▼─────────────────┐
            │  yacy (Java fork) │  │  yacy-vector-service   │
            │  - public UI      │  │  (FastAPI, port 8001)  │
            │  - admin pages    │  │  - /rank (60/25/15)    │
            │  - Solr index     │  │  - /search semantic    │
            │  - crawler        │  │  - /track-search,      │
            │  - P2P + DHT      │  │    /track-click        │
            │  - native UserDB  │  │  - /unsatisfied[/seed] │
            │    (WEBMASTER)    │  │  - /admin/services …   │
            └─────────┬─────────┘  └──────┬─────────────────┘
                      │ Solr               │
                      └──────────┐  ┌──────┘
                                 │  │
                       ┌─────────▼──▼────────────┐
                       │  pgvector (768d)        │
                       │  + query_logs           │
                       │  + query_clicks         │
                       │  + services_menu        │
                       └─────────────────────────┘
```

No external SSO. No client-side tracking. No third-party JS/CSS.

---

## Key features

- **Hybrid ranking** — `intfloat/multilingual-e5-base` (768-dim,
  multilingual, runs locally) hybridised with Solr BM25:
  60% semantic + 25% freshness (recip half-life) + 15% domain quality.
  Cross-lingual queries work (UA query → EN doc and vice versa).
- **No PageRank boost** — `coeff_authority = 0`, `coeff_citation = 0`
  in `RankingProfile`. SEO-link-farms stop dominating.
- **Freshness, properly** — Solr boostfunction
  `recip(ms(NOW,load_date_dt),3.16e-11,1,1)` (≈ 1-year half-life), so
  10-year-old archive pages don't bury this week's news.
- **Sharper blacklist** — `defaults/list.black` ships 401 entries
  (porn / casino / gambling / state-affiliated / mainstream-tracking).
  Active for **CRAWLER, PROXY, SEARCH, DHT, NEWS** simultaneously.
- **Outbound DHT filter** — even when `allowDistributeIndex = true`,
  references whose URL matches the DHT blacklist are dropped before
  the chunk is split for transmission. We share our index without
  leaking trash to the network. (`Dispatcher.filterDhtBlacklisted`)
- **Webmaster pipeline** — public `/Register.html?webmaster=1` self-signup,
  one-click "become webmaster" toggle, `/CrawlRequest.html` to submit a
  domain, admin queue at `/CrawlRequests_p.html` with substring
  blacklist + HEAD-alive bot validator (in-process Java, no extra
  service). LLM zero-shot category check is opt-in via `LLM_API_URL`.
- **Self-healing index** — `cron-unsat-seed.sh` (daily, 03:00 UTC)
  pulls top zero-click queries from `query_logs`, asks an LLM for seed
  URLs, validates them against the blacklist, posts to YaCy crawl
  queue. No-op until you set `LLM_API_KEY`. BYO DeepSeek / OpenAI /
  any OpenAI-compat endpoint.
- **Auto-deploy** — `git push` on the operator branch → ≤5 min in
  production. The deploy script diff-rebuilds only changed services.

---

## Deploy your own

5-minute install on any Ubuntu/Debian box with Docker — see
[`deploy/README.md`](deploy/README.md).

```bash
git clone -b feature/remove-third-party-links \
    https://github.com/VladlenVeronov/yacy_search_server.git yacy-fork
cp yacy-fork/deploy/docker-compose.yml ./
cp yacy-fork/deploy/.env.example ./.env
nano .env    # YACY_HOST, POSTGRES_PASSWORD, ADMIN_TOKEN; LLM keys optional
docker network create traefik-public 2>/dev/null
docker compose up -d
```

The stack is three containers (`yacy`, `yacy-vector-service`,
`yacy-pgvector`) plus your own Traefik for TLS. ~3 GB RAM at idle, more
as you crawl.

LLM keys (DeepSeek / OpenAI-compat / Ollama) and `YACY_ADMIN_USER` /
`YACY_ADMIN_PASS` for `cron-unsat-seed.sh` go in the same `.env` —
never committed.

---

## Project docs

| file                                  | what                                              |
|---------------------------------------|---------------------------------------------------|
| `docs/yacy-project/PLAN.md`           | phase-by-phase roadmap                            |
| `docs/yacy-project/VISION.md`         | why we forked                                     |
| `docs/yacy-project/AUDIT_htroot.md`   | every htroot file: keep / rewrite / drop          |
| `docs/yacy-project/ISSUES.md`         | bug log + critical findings (OOM snippet, …)      |
| `docs/yacy-project/P2P-AUDIT.md`      | DHT share path, blacklist filter, repute deferred |
| `deploy/README.md`                    | install + cron + secrets                          |

---

## Origin / credits

Forked from [`yacy/yacy_search_server`](https://github.com/yacy/yacy_search_server).
The Java core, P2P protocol, Solr integration and crawler are upstream
YaCy. The `vector_service/`, the Tailwind public UI in `htroot/`, the
DHT outbound blacklist filter, the webmaster pipeline (Register /
CrawlRequest / CrawlRequests_p / WebmasterStats), the freshness boost
function, and the `deploy/` reference are VIR GOO additions.

GPL-2.0 (same as upstream YaCy).
