# VIR GOO — promo materials

## Hacker News (Show HN)

**Title (≤ 80 chars):**
> Show HN: VIR GOO – a YaCy fork that drops PageRank and uses semantic search

**Text:**
```
VIR GOO is a fork of YaCy, the open-source P2P search engine, with three
material changes:

1. PageRank/backlink ranking is gone. coeff_authority and coeff_citation
   in YaCy's RankingProfile are zeroed. The Google-style advantage of
   sites with many incoming links no longer applies.

2. Semantic ranking layer added. A FastAPI service with
   intfloat/multilingual-e5-base (768-dim) sits next to Solr. The hybrid
   ranker is 60% semantic similarity + 25% freshness + 15% domain
   quality. Cross-lingual works (UA query → EN doc and vice versa).

3. AI gap-analyzer. Zero-click queries are collected, sent to an LLM
   (DeepSeek/OpenAI-compat, BYO key), which proposes seed URLs. Daily
   cron crawls them. The index heals its own gaps.

Plus: Authentik OIDC for user cabinet (saved searches, bookmarks,
subscriptions), a public webmaster submission form with ~400-entry
content blacklist, no third-party JS/CSS, and a 5-minute deploy
(docker compose up -d).

Live: https://search.newsgroup.site
Repo: https://github.com/VladlenVeronov/yacy_search_server
README: https://github.com/.../README-VIR-GOO.md
Deploy guide: https://github.com/.../deploy/README.md

Not trying to replace Google. Trying to be a search engine that doesn't
have a business reason to bury good results under SEO spam. Feedback
welcome on the ranking weights and the blacklist policy.
```

---

## Reddit r/privacy

**Title:**
> An open-source search engine without PageRank or trackers — VIR GOO (YaCy fork)

**Body:**
Same three points as HN, plus:
- Tailwind, fonts, icons all served locally — no third-party fetches at runtime.
- Cloudflare proxy disabled for OIDC paths to avoid bot-challenge
  breaking SSO redirects.
- All admin actions logged to your own Postgres, never sent out.
- Blacklist (porn / casino / state-affiliated outlets / mainstream
  social) is in a single text file, easy to read and modify.

If you want a search engine you fully own, this is a 5-minute install.

---

## Reddit r/degoogle

**Title:**
> Self-hostable search that drops Google-style PageRank — fork of YaCy

(same body)

---

## Reddit r/selfhosted

**Title:**
> VIR GOO: docker compose up -d → your own decentralized search engine

**Body:**
Components:
- yacy (Java fork) — public UI + crawler + Solr
- vector_service (FastAPI) — semantic ranking + cabinet + admin
- pgvector (Postgres 16) — embeddings + analytics
- Authentik (separate stack on auth.yourdomain) — OIDC for users
- traefik — TLS via Let's Encrypt

Resources used: ~3GB RAM, 2GB disk for the model + index, more as you crawl.

5-min install: https://.../deploy/README.md

---

## Product Hunt tagline

> Open-source semantic search you can self-host in 5 minutes.

**One-liner:**
A YaCy fork that uses semantic embeddings instead of PageRank, comes with
AI-driven crawl gap-filling, and is fully self-hostable with one
docker compose command.

---

## Twitter/X thread (short)

1/ Built a fork of @YaCy_Search that:
- drops PageRank ranking entirely
- adds semantic search via multilingual-e5
- has an AI loop that fixes its own gaps overnight
- is 5 minutes to self-host

Live: search.newsgroup.site

2/ Ranking is 60% semantic + 25% freshness + 15% URL quality. No backlink
boost. SEO-spam loses its main advantage. (PageRank coefficient = 0
in the source — verifiable in the diff.)

3/ Authentik OIDC for users, public form for site submissions, ~400-entry
content blacklist (porn/casino/state-affiliated outlets/mainstream
social) you can audit and modify yourself.

4/ Repo (GPL-2.0): github.com/VladlenVeronov/yacy_search_server
Branch: feature/remove-third-party-links

5/ Not trying to outscale Google. Trying to be a search engine without a
business reason to hide the best results.
