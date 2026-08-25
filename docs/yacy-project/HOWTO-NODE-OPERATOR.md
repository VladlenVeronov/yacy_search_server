# How to run your own VIR GOO peer

This is for **operators** — the people who want a search node, not just
users of `search.newsgroup.site`. After this guide you will have:

* Your own `https://search.<your-domain>/` mirror.
* Your peer joined to the YaCy `freeworld` P2P network.
* Outbound DHT shares filtered against the content blacklist (so you
  don't ship spam to the network).
* Your peer answering inbound queries from other peers.

---

## 1. Hardware

Minimum to be useful:

| resource | recommended | what it's for                                    |
|----------|-------------|--------------------------------------------------|
| CPU      | 4 cores     | Solr indexing, vector_service embeddings         |
| RAM      | 6 GB        | YaCy 2 GB + e5 model 1 GB + Postgres 1 GB + slack |
| Disk     | 20 GB       | Index + embeddings (1k pages ≈ 30 MB)            |
| OS       | Linux + Docker 24+ | the only tested platform                  |

Smaller than that works for hobby use; smaller than 2 GB RAM is not
worth the pain.

---

## 2. Install (5 minutes)

```bash
# 1. clone the fork
git clone -b feature/remove-third-party-links \
    https://github.com/VladlenVeronov/yacy_search_server.git yacy-fork

# 2. copy compose + env template into your stack dir
mkdir -p ~/stacks/yacy && cd ~/stacks/yacy
cp yacy-fork/deploy/docker-compose.yml ./
cp yacy-fork/deploy/.env.example ./.env

# 3. fill secrets
nano .env
# YACY_HOST=search.your-domain.tld
# POSTGRES_PASSWORD=$(openssl rand -hex 16)
# ADMIN_TOKEN=$(openssl rand -hex 24)
# (LLM_API_URL/KEY optional — leave empty unless you want gap-fill)
# (YACY_ADMIN_USER/PASS only needed for cron-unsat-seed.sh)

# 4. ensure the traefik network exists (or adapt the labels to nginx etc.)
docker network create traefik-public 2>/dev/null

# 5. up
docker compose up -d
```

Watch logs:

```bash
docker compose logs -f yacy
```

You should see, within ~60 s:

```
NETWORK * BOOTSTRAP: 1xx seeds loaded from URL …yacy/seed.txt
NETWORK * normalize ‘freeworld' network seed list to size N
```

---

## 3. Joining the network

The default `network.unit.name` is **freeworld** — the public YaCy
network. On boot YaCy fetches the seed-list from a few well-known URLs
and starts handshaking with the peers it can reach.

Verify in the admin UI:

* `/Network.html` — should list ≥ 50 visible peers within an hour.
* `/Status.html` — `Network` row says `freeworld, junior` initially,
  promotes to `senior` once you start serving and replying.

If you get stuck at 0 peers:

* Outbound 80/443 must be open. UDP is **not** required.
* Outbound 8090 (or whatever you mapped) must be reachable from the
  internet for inbound peer connections. Test via
  `https://search.your-domain.tld/yacy/` — should return XML status.
* If you're behind a strict NAT and can't open inbound, you'll be
  `principal/junior` indefinitely — outbound queries still work, just
  slower.

---

## 4. Sharing posture (this fork's defaults)

This fork ships **safer-than-upstream** defaults; the operator can
loosen them via `/IndexShare_p.html` if they want.

| key                            | shipped value | meaning                                     |
|--------------------------------|---------------|---------------------------------------------|
| `allowDistributeIndex`         | true          | We share our index out via DHT.             |
| `allowReceiveIndex`            | **false**     | We don't accept incoming DHT shares.        |
| `60_remotecrawlloader_isPaused`| **true**      | We don't run other peers' crawl jobs.       |
| `indexReceiveBlockBlacklist`   | true          | DHT-receive (if ever enabled) is blacklisted. |

Plus the outbound DHT filter — **new in this fork** — drops references
to URLs that match `BlacklistType.DHT` *before* the chunk is split for
transmission. See `docs/yacy-project/P2P-AUDIT.md` for the share-path
code map.

---

## 5. Crawler setup

Out of the box your peer indexes nothing. Two paths to first index:

**(a) Curated seed list** — the upstream-recommended path:

1. Open `/CrawlStartExpert.html`.
2. Crawling URL: a single page or sitemap entry.
3. `crawlingMustMatch`: a regex pinning the crawl to vetted hosts.
4. Depth: 3–5.
5. **Don't tick** "Do remote crawl" unless you trust the network's
   request stream.

**(b) Self-signup webmaster pipeline** (also in this fork):

* Operators leave `/Register.html?webmaster=1` open to the public.
* Site owners self-submit at `/CrawlRequest.html`.
* Bot validator + admin queue at `/CrawlRequests_p.html` decides what
  actually crawls.

See `docs/yacy-project/HOWTO-WEBMASTER.md` for the user-facing flow.

---

## 6. Background jobs

Three crons recommended on the host (any user that owns the stack):

```bash
( crontab -l 2>/dev/null
  echo "*/5 * * * * STACK_DIR=$PWD $PWD/deploy/auto-deploy.sh"
  echo  "5 * * * * STACK_DIR=$PWD $PWD/deploy/cron-sync-pages.sh"
  echo  "0 3 * * * STACK_DIR=$PWD $PWD/deploy/cron-unsat-seed.sh"
) | crontab -
```

* `auto-deploy.sh` — git pull + rebuild changed services.
* `cron-sync-pages.sh` — Solr → pgvector incremental sync.
* `cron-unsat-seed.sh` — LLM gap-fill (no-op unless `LLM_API_URL`/`KEY`).

---

## 7. Operating

| URL                      | who    | what                                   |
|--------------------------|--------|----------------------------------------|
| `/`                      | public | Search homepage                        |
| `/yacysearch.html?…`     | public | Search results                         |
| `/Register.html`         | public | Self-signup (+ optional webmaster)     |
| `/User.html`             | public | Login                                  |
| `/CrawlRequest.html`     | webmaster | Submit a domain                     |
| `/WebmasterStats.html`   | webmaster | Per-host stats (own domains)        |
| `/CrawlRequests_p.html`  | admin  | Submission queue + bot validator       |
| `/Analytics_p.html`      | admin  | vector_service health + zero-clicks    |
| `/Status.html`           | admin  | YaCy core status                       |
| `/Network.html`          | admin  | Peer list                              |
| `/IndexShare_p.html`     | admin  | Distribute / receive toggles           |
| `/Performance_p.html`    | admin  | Process scheduler tuning               |

The admin path requires the YaCy digest-auth credentials set during
first-boot wizard at `/ConfigBasic.html`.

---

## 8. Troubleshooting

| symptom                                          | check                                                   |
|--------------------------------------------------|---------------------------------------------------------|
| Peer stays at 0 visible peers for > 1 h          | Outbound HTTPS to `seed-list` URLs blocked? `iptables -L` |
| Search returns 0 results from a small index      | `/Status.html` — Solr healthy? `boostfunction` set?     |
| `/api/vector/health` returns 502                 | `docker compose logs yacy-vector-service` — model load? |
| All UI pages still look like Bootstrap          | YaCy serves cached translated templates from `DATA/LOCALE/htroot/<lang>/`. `rm -f` the affected file and reload. |
| `cron-sync-pages.log` says "previous still running" | Initial sync of a large index can take hours — let it finish.  |

For anything else, log + commit hash + which step failed → file an
issue at `github.com/VladlenVeronov/yacy_search_server/issues`.
