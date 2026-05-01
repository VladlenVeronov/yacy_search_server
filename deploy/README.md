# Production deployment — VIR GOO / YACY fork

This directory ships everything needed to stand up the public stack on a
fresh server with **no secrets in the repo**. Real values live in
`./.env` on the server (gitignored). Use `.env.example` as the template.

## Stack

Three containers behind Traefik:

| service              | image                                  | role                                          |
|----------------------|----------------------------------------|-----------------------------------------------|
| `yacy`               | built from `yacy-fork/docker/Dockerfile` | YaCy (this fork) — public search UI          |
| `yacy-vector-service`| built from `yacy-fork/vector_service/Dockerfile` | FastAPI semantic ranker, services menu CRUD, search-tracking |
| `yacy-pgvector`      | `pgvector/pgvector:pg16`               | Postgres + pgvector for embeddings + analytics |

Public routing (Traefik labels):
- `https://${YACY_HOST}/`              → `yacy:8090`
- `https://${YACY_HOST}/api/vector/*`  → `yacy-vector-service:8001` (StripPrefix)

## First-time install

```bash
sudo mkdir -p /opt/yacy && sudo chown $USER /opt/yacy
cd /opt/yacy

# 1. clone this fork
git clone -b feature/remove-third-party-links \
    https://github.com/VladlenVeronov/yacy_search_server.git yacy-fork

# 2. copy compose + env template
cp yacy-fork/deploy/docker-compose.yml ./
cp yacy-fork/deploy/.env.example ./.env

# 3. fill secrets
nano .env   # set YACY_HOST, POSTGRES_PASSWORD (`openssl rand -hex 16`),
            # ADMIN_TOKEN (`openssl rand -hex 24`)

# 4. ensure traefik-public network exists (or adapt to your reverse proxy)
docker network inspect traefik-public >/dev/null 2>&1 || \
    docker network create traefik-public

# 5. build + bring up
docker compose build
docker compose up -d

# 6. (optional) wire automatic git→deploy
cp yacy-fork/deploy/auto-deploy.sh ./deploy/
chmod +x ./deploy/auto-deploy.sh
( crontab -l 2>/dev/null; echo "*/5 * * * * STACK_DIR=/opt/yacy /opt/yacy/deploy/auto-deploy.sh" ) | crontab -
```

## Updating

If `auto-deploy.sh` is on cron, just `git push` and wait ≤5 min. Manual:

```bash
cd /opt/yacy
STACK_DIR=$PWD ./deploy/auto-deploy.sh
tail /opt/yacy/deploy/auto-deploy.log
```

The script:
1. fetches the configured branch (`feature/remove-third-party-links` by default),
2. exits if HEAD didn't move,
3. detects which services need rebuilding from the diff
   (`htroot/`/`source/`/`docker/Dockerfile` → `yacy`; `vector_service/` → `yacy-vector-service`),
4. re-applies `schema.sql` (idempotent),
5. brings the stack up.

## Secrets

| where                        | contains                              | gitignored? |
|------------------------------|---------------------------------------|-------------|
| `./.env` (server only)       | YACY_HOST, POSTGRES_PASSWORD, ADMIN_TOKEN | yes        |
| `./yacy-data/SETTINGS/`      | YaCy admin password hash, **LLM API keys** entered via UI | yes (under `/DATA`) |
| pgvector volume              | embeddings + query logs               | yes (named docker volume) |

LLM API keys (DeepSeek, OpenAI, Ollama, …) are **never set in the repo or
in `.env`**. They're entered through the YaCy admin UI at
`https://${YACY_HOST}/LLMSelection_p.html` and persisted into
`yacy-data/SETTINGS/yacy.conf`. Treat the host's `yacy-data/` as secret.

## Forking this for your own deployment

Everything in `deploy/` is the public reference. Clone the fork, copy
`.env.example → .env`, fill your own secrets, and you have an
independent VIR GOO / YACY instance. No values committed here belong to
anyone — you supply your own host, your own Postgres password, your own
admin token, and your own LLM keys.
