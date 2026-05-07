# VIR GOO — promo materials

## Hacker News (Show HN)

**Title (≤ 80 chars):**
> Show HN: VIR GOO – a YaCy fork that drops PageRank and uses semantic search

**Text:**
```
VIR GOO is a fork of YaCy, the open-source P2P search engine, with four
material changes:

1. PageRank/backlink ranking is gone. coeff_authority and coeff_citation
   in YaCy's RankingProfile are zeroed. The Google-style advantage of
   sites with many incoming links no longer applies.

2. Semantic ranking layer added. A FastAPI service with
   intfloat/multilingual-e5-base (768-dim, runs locally — no third-party
   inference at runtime) sits next to Solr. The hybrid ranker is
   60% semantic similarity + 25% freshness + 15% domain quality.
   Cross-lingual works (UA query → EN doc and vice versa).

3. AI gap-analyzer. Zero-click queries are collected, sent to an LLM
   (DeepSeek/OpenAI-compat, BYO key), which proposes seed URLs.
   Daily cron crawls them. The index heals its own gaps.

4. Outbound DHT share filter. Upstream YaCy can distribute its index
   to peers; we keep that on, but added a blacklist check so refs to
   porn/casino/spam hosts are dropped before transmission. We share
   our index without polluting the network.

Plus: native YaCy UserDB self-signup with a "webmaster" role, public
crawl-request form with an in-process Java bot validator, ~400-entry
content blacklist active simultaneously on CRAWLER/PROXY/SEARCH/DHT/NEWS,
no third-party JS/CSS at runtime, and a 5-minute deploy
(docker compose up -d).

Live: https://search.newsgroup.site
Repo: https://github.com/VladlenVeronov/yacy_search_server
README: https://github.com/.../README-VIR-GOO.md
Deploy guide: https://github.com/.../deploy/README.md

Not trying to replace Google. Trying to be a search engine that doesn't
have a business reason to bury good results under SEO spam. Feedback
welcome on the ranking weights, the blacklist policy, and the DHT
share-filter coverage.
```

---

## Reddit r/privacy

**Title:**
> An open-source search engine without PageRank or trackers — VIR GOO (YaCy fork)

**Body:**
Same four points as HN, plus:
- Tailwind, fonts, icons all served locally — no third-party fetches at runtime.
- All admin actions logged to your own Postgres, never sent out.
- Blacklist (porn / casino / state-affiliated outlets / mainstream
  social) is in a single text file, easy to read and modify.
- DHT outbound: blacklisted hosts never reach peer indexes.

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
- yacy (Java fork) — public UI + crawler + Solr index + P2P
- vector_service (FastAPI) — semantic ranking + analytics + services CRUD
- pgvector (Postgres 16) — embeddings + query analytics

Resources used: ~3 GB RAM at idle, 2 GB disk for the model + index,
more as you crawl. No external dependencies — bring your own Traefik.

5-min install: https://.../deploy/README.md

---

## Product Hunt tagline

> Open-source semantic search you can self-host in 5 minutes.

**One-liner:**
A YaCy fork that uses semantic embeddings instead of PageRank, comes
with AI-driven crawl gap-filling, filters its outbound peer-shares
against a content blacklist, and is fully self-hostable with one
docker compose command.

---

## Twitter/X thread (short)

1/ Built a fork of @YaCy_Search that:
- drops PageRank ranking entirely
- adds semantic search via multilingual-e5 (runs locally)
- has an AI loop that fixes its own index gaps overnight
- filters outbound P2P shares against a content blacklist
- is 5 minutes to self-host

Live: search.newsgroup.site

2/ Ranking is 60% semantic + 25% freshness + 15% URL quality. No backlink
boost. SEO-spam loses its main advantage. (PageRank coefficient = 0
in the source — verifiable in the diff.)

3/ Public webmaster onboarding via native YaCy UserDB self-signup; an
in-process Java bot validator (substring blacklist + HEAD-alive) gates
the crawl queue. ~400-entry content blacklist active on
CRAWLER/PROXY/SEARCH/DHT/NEWS simultaneously.

4/ Repo (GPL-2.0): github.com/VladlenVeronov/yacy_search_server
Branch: feature/remove-third-party-links

5/ Not trying to outscale Google. Trying to be a search engine without a
business reason to hide the best results.
