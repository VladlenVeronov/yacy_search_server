from __future__ import annotations

import hashlib
import math
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from config import settings
from db import close_pool, init_pool, pool
from embedder import embed_passages, embed_query, get_model


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_model()  # warm the embedding model so the first /search isn't slow
    await init_pool()
    yield
    await close_pool()


app = FastAPI(title="YACY Vector Service", version="0.1.0", lifespan=lifespan)


class IndexRequest(BaseModel):
    id: str = Field(..., min_length=1)
    url: str
    title: Optional[str] = None
    summary: str
    host: Optional[str] = None
    lang: Optional[str] = None
    last_modified: Optional[datetime] = None  # ISO8601 in JSON


class IndexResponse(BaseModel):
    id: str
    embedded: bool


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(default=20, ge=1, le=200)


class SearchHit(BaseModel):
    id: str
    url: str
    title: Optional[str] = None
    host: Optional[str] = None
    score: float


@app.get("/health")
async def health():
    async with pool().acquire() as con:
        await con.execute("SELECT 1")
    return {"ok": True, "model": settings.embedding_model, "dim": settings.embedding_dim}


@app.post("/index", response_model=IndexResponse)
async def index(req: IndexRequest):
    summary = req.summary[: settings.max_summary_chars]
    if not summary.strip():
        raise HTTPException(status_code=400, detail="summary is empty")
    chash = hashlib.sha256(summary.encode("utf-8")).hexdigest()

    async with pool().acquire() as con:
        existing = await con.fetchrow(
            "SELECT content_hash FROM pages WHERE id=$1", req.id
        )
        if existing is not None and existing["content_hash"] == chash:
            return IndexResponse(id=req.id, embedded=False)

        embedding = (await embed_passages([summary]))[0]
        await con.execute(
            """
            INSERT INTO pages (id, url, host, title, summary, content_hash,
                               last_modified, lang, embedding, embedded_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, now())
            ON CONFLICT (id) DO UPDATE SET
                url = EXCLUDED.url,
                host = EXCLUDED.host,
                title = EXCLUDED.title,
                summary = EXCLUDED.summary,
                content_hash = EXCLUDED.content_hash,
                last_modified = EXCLUDED.last_modified,
                lang = EXCLUDED.lang,
                embedding = EXCLUDED.embedding,
                embedded_at = now()
            """,
            req.id, req.url, req.host, req.title, summary, chash,
            req.last_modified, req.lang, embedding,
        )
    return IndexResponse(id=req.id, embedded=True)


@app.post("/search", response_model=list[SearchHit])
async def search(req: SearchRequest):
    qvec = await embed_query(req.query)
    async with pool().acquire() as con:
        rows = await con.fetch(
            """
            SELECT id, url, title, host,
                   1 - (embedding <=> $1) AS score
              FROM pages
             WHERE embedding IS NOT NULL
             ORDER BY embedding <=> $1
             LIMIT $2
            """,
            qvec, req.limit,
        )
    return [SearchHit(**dict(row)) for row in rows]


@app.delete("/doc/{doc_id}")
async def delete(doc_id: str):
    async with pool().acquire() as con:
        result = await con.execute("DELETE FROM pages WHERE id=$1", doc_id)
    deleted = result.split()[-1] if result else "0"
    return {"deleted": int(deleted)}


# ---------------------------------------------------------------------------
# Hybrid re-ranking
# ---------------------------------------------------------------------------


class RankCandidate(BaseModel):
    id: str = Field(..., min_length=1)
    url: Optional[str] = None
    last_modified: Optional[datetime] = None


class RankRequest(BaseModel):
    query: str = Field(..., min_length=1)
    candidates: list[RankCandidate] = Field(..., min_length=1, max_length=500)
    limit: Optional[int] = Field(default=None, ge=1, le=500)


class RankHit(BaseModel):
    id: str
    score: float
    semantic: float
    freshness: float
    quality: float
    embedded: bool


def _freshness_score(last_modified: Optional[datetime]) -> float:
    """Exponential decay on document age. Missing date → neutral 0.5 so the
    component neither helps nor hurts."""
    if last_modified is None:
        return 0.5
    if last_modified.tzinfo is None:
        last_modified = last_modified.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - last_modified).total_seconds() / 86400.0
    if age_days <= 0:
        return 1.0
    decay = math.exp(-age_days / settings.freshness_half_life_days)
    return max(0.0, min(1.0, decay))


def _quality_score(url: Optional[str]) -> float:
    """Lightweight URL-only quality signal — HTTPS gets full credit, HTTP a
    sharp penalty. Real signals (page speed, ad/tracker presence) need
    crawl-time data not yet available here; this is a placeholder slot in
    the hybrid weight so adding them later is a one-line change."""
    if not url:
        return 0.5
    try:
        scheme = urlparse(url).scheme.lower()
    except ValueError:
        return 0.3
    if scheme == "https":
        return 1.0
    if scheme == "http":
        return 0.3
    return 0.5


@app.post("/rank", response_model=list[RankHit])
async def rank(req: RankRequest):
    qvec = await embed_query(req.query)
    ids = [c.id for c in req.candidates]
    by_id = {c.id: c for c in req.candidates}

    async with pool().acquire() as con:
        rows = await con.fetch(
            """
            SELECT id,
                   1 - (embedding <=> $1) AS sim,
                   url,
                   last_modified
              FROM pages
             WHERE id = ANY($2::text[])
               AND embedding IS NOT NULL
            """,
            qvec, ids,
        )
    pg = {r["id"]: r for r in rows}

    ws, wf, wq = settings.weight_semantic, settings.weight_freshness, settings.weight_quality
    hits: list[RankHit] = []
    for cand in req.candidates:
        row = pg.get(cand.id)
        if row is not None:
            # e5 cosine sim is ~[0, 1] for related pairs; clip negatives.
            semantic = max(0.0, min(1.0, float(row["sim"])))
            url = cand.url or row["url"]
            last_mod = cand.last_modified or row["last_modified"]
            embedded = True
        else:
            semantic = 0.0
            url = cand.url
            last_mod = cand.last_modified
            embedded = False

        freshness = _freshness_score(last_mod)
        quality = _quality_score(url)
        score = ws * semantic + wf * freshness + wq * quality
        hits.append(RankHit(
            id=cand.id,
            score=score,
            semantic=semantic,
            freshness=freshness,
            quality=quality,
            embedded=embedded,
        ))

    hits.sort(key=lambda h: h.score, reverse=True)
    if req.limit is not None:
        hits = hits[: req.limit]
    return hits


# ---------------------------------------------------------------------------
# Search analytics: feeds autocomplete and the unsatisfied-query crawler
# ---------------------------------------------------------------------------


class TrackSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    result_count: int = Field(default=0, ge=0)


class TrackClickRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    doc_id: Optional[str] = None
    url: Optional[str] = None
    position: Optional[int] = Field(default=None, ge=0)


@app.post("/track-search")
async def track_search(req: TrackSearchRequest):
    async with pool().acquire() as con:
        await con.execute(
            "INSERT INTO query_logs (query, result_count) VALUES ($1, $2)",
            req.query.strip(), req.result_count,
        )
    return {"ok": True}


@app.post("/track-click")
async def track_click(req: TrackClickRequest):
    q = req.query.strip()
    async with pool().acquire() as con:
        async with con.transaction():
            await con.execute(
                """
                INSERT INTO query_clicks (query, doc_id, url, position)
                VALUES ($1, $2, $3, $4)
                """,
                q, req.doc_id, req.url, req.position,
            )
            # Bump click count on the most recent matching log entry so the
            # /unsatisfied query can use it directly.
            await con.execute(
                """
                UPDATE query_logs SET clicked_count = clicked_count + 1
                 WHERE id = (
                    SELECT id FROM query_logs
                     WHERE lower(query) = lower($1)
                     ORDER BY ts DESC LIMIT 1
                 )
                """,
                q,
            )
    return {"ok": True}


# ---------------------------------------------------------------------------
# Webmaster submissions (Phase 3)
# ---------------------------------------------------------------------------


# Substring patterns picked up from yacy DATA/LISTS/list.black at startup.
# We don't try to perfectly mirror YaCy's regex matcher — a substring check
# is enough to reject the obvious cases at submission time. The crawler
# itself is the real authority.
_BLACKLIST_HINTS = (
    "wikipedia", "wikimedia", "wikidata", "wikinews", "wikiquote",
    "wikiversity", "wikivoyage", "wiktionary", "wikibooks", "mediawiki",
    "facebook", "instagram", "tiktok", "twitter", "x.com", "youtube",
    "reddit", "quora", "pinterest", "linkedin",
    "amazon", "ebay", "aliexpress", "wish.com", "dhgate", "banggood",
    "shein", "temu",
    "rt.com", "rt.ru", "sputnik", "tass.ru", "ria.ru", "vesti.ru",
    "1tv.ru", "russia.tv", "ntv.ru", "lenta.ru", "regnum.ru",
    "tsargrad.tv", "ren.tv", "kommersant.ru", "gazeta.ru", "iz.ru",
    "kp.ru", "aif.ru", "life.ru", "novayagazeta.ru", "fontanka.ru",
    "meduza.io", "pravda.ru", "smart-lab.ru", "3dnews.ru",
    "porn", "xxx", "xnxx", "xvideos", "xhamster", "brazzers", "onlyfans",
    "chaturbate", "redtube", "youporn", "pornhub", "spankbang",
    "tube8", "eporner", "beeg", "cam4", "livejasmin",
    "bis.org", "ecb.europa.eu", "federalreserve.gov", "imf.org",
    "worldbank.org", "weforum.org", "atlanticcouncil.org", "globalresearch.ca",
)


def _classify_url(url: str) -> tuple[str, Optional[str]]:
    """Returns (host, reject_reason). reject_reason is None if accepted."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return ("", "malformed url")
    if parsed.scheme not in ("http", "https"):
        return ("", "scheme must be http(s)")
    host = (parsed.hostname or "").lower()
    if not host or "." not in host:
        return (host, "missing/invalid host")
    lower_url = url.lower()
    for hint in _BLACKLIST_HINTS:
        if hint in lower_url:
            return (host, f"matches blacklist hint: {hint}")
    return (host, None)


class SubmitSiteRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=500)
    contact_email: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)


class SubmissionItem(BaseModel):
    id: int
    url: str
    host: str
    contact_email: Optional[str] = None
    description: Optional[str] = None
    status: str
    priority: str = "normal"
    reject_reason: Optional[str] = None
    submitted_at: datetime
    processed_at: Optional[datetime] = None


@app.post("/submit-site")
async def submit_site(req: SubmitSiteRequest):
    host, reject = _classify_url(req.url.strip())
    initial_status = "rejected" if reject else "pending"
    async with pool().acquire() as con:
        # Reject duplicate pending submissions for the same host within 7 days
        # so the public form can't be used to flood the admin queue.
        if not reject:
            dup = await con.fetchval(
                """
                SELECT id FROM webmaster_submissions
                 WHERE host = $1
                   AND status IN ('pending', 'approved', 'crawled')
                   AND submitted_at > now() - interval '7 days'
                 LIMIT 1
                """, host,
            )
            if dup:
                return {"ok": False, "status": "duplicate",
                        "message": "This host was already submitted in the last 7 days."}
        row = await con.fetchrow(
            """
            INSERT INTO webmaster_submissions
                (url, host, contact_email, description, status, reject_reason)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, status
            """,
            req.url.strip(), host, req.contact_email, req.description,
            initial_status, reject,
        )
    return {"ok": True, "id": row["id"], "status": row["status"], "reject_reason": reject}


@app.get("/admin/submissions", response_model=list[SubmissionItem])
async def submissions_list(status: Optional[str] = None, limit: int = 200,
                            authorization: Optional[str] = Header(default=None)):
    _require_admin(authorization)
    where = "WHERE status = $1" if status else ""
    args: list = [status] if status else []
    args.append(limit)
    n = len(args)
    async with pool().acquire() as con:
        rows = await con.fetch(
            f"""
            SELECT id, url, host, contact_email, description, status, priority,
                   reject_reason, submitted_at, processed_at
              FROM webmaster_submissions
              {where}
             ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END, submitted_at DESC
             LIMIT ${n}
            """, *args,
        )
    return [SubmissionItem(**dict(r)) for r in rows]


@app.post("/admin/submissions/{sub_id}/decision")
async def submissions_decide(sub_id: int,
                              decision: str,
                              reason: Optional[str] = None,
                              authorization: Optional[str] = Header(default=None)):
    _require_admin(authorization)
    if decision not in ("approved", "rejected", "crawled"):
        raise HTTPException(status_code=400, detail="decision must be approved|rejected|crawled")
    async with pool().acquire() as con:
        row = await con.fetchrow(
            """
            UPDATE webmaster_submissions
               SET status = $2,
                   reject_reason = $3,
                   processed_at = now()
             WHERE id = $1
            RETURNING id, status
            """, sub_id, decision, reason,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True, **dict(row)}


@app.post("/admin/submissions/{sub_id}/priority")
async def submissions_priority(sub_id: int, priority: str,
                                authorization: Optional[str] = Header(default=None)):
    _require_admin(authorization)
    if priority not in ("high", "normal", "low"):
        raise HTTPException(status_code=400, detail="priority must be high|normal|low")
    async with pool().acquire() as con:
        row = await con.fetchrow(
            "UPDATE webmaster_submissions SET priority=$2 WHERE id=$1 RETURNING id, priority",
            sub_id, priority,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True, **dict(row)}


# ---------------------------------------------------------------------------
# Services menu (Phase 3 admin)
# ---------------------------------------------------------------------------


def _require_admin(authorization: Optional[str]) -> None:
    if not settings.admin_token:
        raise HTTPException(status_code=503, detail="admin token not configured")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    if authorization.split(None, 1)[1].strip() != settings.admin_token:
        raise HTTPException(status_code=403, detail="invalid token")


class ServiceItem(BaseModel):
    id: int
    name: str
    url: str
    icon_url: Optional[str] = None
    sort_order: int = 0
    active: bool = True


class ServiceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    url: str = Field(..., min_length=1, max_length=500)
    icon_url: Optional[str] = Field(default=None, max_length=500)
    sort_order: int = 0
    active: bool = True


class ServiceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    url: Optional[str] = Field(default=None, min_length=1, max_length=500)
    icon_url: Optional[str] = Field(default=None, max_length=500)
    sort_order: Optional[int] = None
    active: Optional[bool] = None


@app.get("/services", response_model=list[ServiceItem])
async def services_list(include_inactive: bool = False):
    where = "" if include_inactive else "WHERE active = true"
    async with pool().acquire() as con:
        rows = await con.fetch(
            f"SELECT id,name,url,icon_url,sort_order,active FROM services_menu {where} ORDER BY sort_order ASC, id ASC"
        )
    return [ServiceItem(**dict(r)) for r in rows]


@app.post("/admin/services", response_model=ServiceItem)
async def services_create(req: ServiceCreate, authorization: Optional[str] = Header(default=None)):
    _require_admin(authorization)
    async with pool().acquire() as con:
        row = await con.fetchrow(
            """
            INSERT INTO services_menu (name, url, icon_url, sort_order, active)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, name, url, icon_url, sort_order, active
            """,
            req.name, req.url, req.icon_url, req.sort_order, req.active,
        )
    return ServiceItem(**dict(row))


@app.put("/admin/services/{svc_id}", response_model=ServiceItem)
async def services_update(svc_id: int, req: ServiceUpdate, authorization: Optional[str] = Header(default=None)):
    _require_admin(authorization)
    fields = req.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="no fields to update")
    sets = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(fields))
    sets += ", updated_at = now()"
    async with pool().acquire() as con:
        row = await con.fetchrow(
            f"UPDATE services_menu SET {sets} WHERE id = $1 RETURNING id,name,url,icon_url,sort_order,active",
            svc_id, *fields.values(),
        )
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return ServiceItem(**dict(row))


@app.delete("/admin/services/{svc_id}")
async def services_delete(svc_id: int, authorization: Optional[str] = Header(default=None)):
    _require_admin(authorization)
    async with pool().acquire() as con:
        result = await con.execute("DELETE FROM services_menu WHERE id = $1", svc_id)
    return {"deleted": int(result.split()[-1]) if result else 0}


# ---------------------------------------------------------------------------
# AI gap analyzer: unsatisfied queries -> LLM -> seed URLs
# ---------------------------------------------------------------------------


_LLM_PROMPT = (
    "You are helping curate seed URLs for a privacy-respecting, decentralized "
    "search index. Given a user search query that returned zero clicks, "
    "propose 3 to 5 high-quality, openly accessible URLs that would directly "
    "satisfy that query. Hard constraints:\n"
    "- HTTPS only.\n"
    "- No Wikipedia, no Wikimedia, no major social networks (Reddit, X/Twitter, "
    "Facebook, Instagram, TikTok, YouTube, Pinterest, LinkedIn, Quora).\n"
    "- No mainstream e-commerce (Amazon, Aliexpress, eBay, Temu).\n"
    "- No state-affiliated outlets (RT, TASS, RIA, Sputnik, etc).\n"
    "- No porn, casino, or surveillance-heavy news.\n"
    "- Prefer primary sources, official docs, established open-source projects, "
    "EFF/FSF/IETF/RFC-style references, well-curated personal blogs.\n"
    "Return JSON: {\"urls\": [\"https://...\", ...]} and nothing else."
)


async def _llm_propose_urls(query: str) -> list[str]:
    import json as _json
    import httpx
    if not settings.llm_api_url or not settings.llm_api_key:
        return []
    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": _LLM_PROMPT},
            {"role": "user", "content": query},
        ],
        "temperature": 0.2,
        "max_tokens": 400,
        "response_format": {"type": "json_object"},
    }
    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_s) as cli:
            r = await cli.post(
                settings.llm_api_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            obj = _json.loads(content)
            urls = obj.get("urls", [])
            return [u for u in urls if isinstance(u, str) and u.startswith("https://")]
    except Exception:
        return []


@app.get("/unsatisfied/seed")
async def unsatisfied_seed(limit_queries: int = 10, hours: int = 168,
                            authorization: Optional[str] = Header(default=None)):
    _require_admin(authorization)
    if not settings.llm_api_url:
        raise HTTPException(status_code=503, detail="LLM not configured")
    async with pool().acquire() as con:
        rows = await con.fetch(
            """
            SELECT lower(query) AS query, COUNT(*) AS searches
              FROM query_logs
             WHERE ts > now() - ($1 || ' hours')::interval
             GROUP BY lower(query)
            HAVING SUM(clicked_count) = 0
             ORDER BY searches DESC
             LIMIT $2
            """,
            str(hours), limit_queries,
        )
    plan: list[dict] = []
    for r in rows:
        urls = await _llm_propose_urls(r["query"])
        accepted: list[str] = []
        for u in urls:
            _, reason = _classify_url(u)
            if reason is None:
                accepted.append(u)
        plan.append({
            "query": r["query"],
            "searches": r["searches"],
            "proposed": urls,
            "accepted": accepted,
        })
    return plan


@app.get("/unsatisfied")
async def unsatisfied(hours: int = 168, limit: int = 100):
    """Top recent queries with zero clicks. Crawler picks from this list to
    fill index gaps. Default window: 7 days."""
    async with pool().acquire() as con:
        rows = await con.fetch(
            """
            SELECT lower(query) AS query, COUNT(*) AS searches,
                   SUM(result_count) AS total_results,
                   SUM(clicked_count) AS clicks
              FROM query_logs
             WHERE ts > now() - ($1 || ' hours')::interval
             GROUP BY lower(query)
            HAVING SUM(clicked_count) = 0
             ORDER BY searches DESC
             LIMIT $2
            """,
            str(hours), limit,
        )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# OIDC + User Cabinet (Phase 3)
# ---------------------------------------------------------------------------
import secrets as _secrets
import hashlib as _hashlib
import base64 as _base64
import time as _time
from datetime import timedelta as _td
from fastapi import Request, Response, Cookie
from fastapi.responses import RedirectResponse


_OIDC_DISCOVERY_CACHE: dict = {}


async def _oidc_discovery() -> dict:
    """Fetch and cache OpenID Connect discovery metadata."""
    import httpx
    if not settings.oidc_issuer:
        raise HTTPException(status_code=503, detail="OIDC not configured")
    if "data" not in _OIDC_DISCOVERY_CACHE or _OIDC_DISCOVERY_CACHE.get("ts", 0) < _time.time() - 3600:
        url = settings.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration"
        async with httpx.AsyncClient(timeout=10) as cli:
            r = await cli.get(url)
            r.raise_for_status()
            _OIDC_DISCOVERY_CACHE["data"] = r.json()
            _OIDC_DISCOVERY_CACHE["ts"] = _time.time()
    return _OIDC_DISCOVERY_CACHE["data"]


def _b64url(data: bytes) -> str:
    return _base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@app.get("/oidc/login")
async def oidc_login(return_to: str = "/cabinet.html"):
    if not settings.oidc_issuer:
        raise HTTPException(status_code=503, detail="OIDC not configured")
    disco = await _oidc_discovery()
    state = _secrets.token_urlsafe(24)
    nonce = _secrets.token_urlsafe(24)
    # PKCE S256 — Authentik supports it; harmless for confidential clients.
    code_verifier = _secrets.token_urlsafe(48)
    code_challenge = _b64url(_hashlib.sha256(code_verifier.encode()).digest())
    async with pool().acquire() as con:
        await con.execute(
            "INSERT INTO cabinet_oidc_state (state, nonce, code_verifier, return_to) VALUES ($1,$2,$3,$4)",
            state, nonce, code_verifier, return_to,
        )
    from urllib.parse import urlencode
    qs = urlencode({
        "response_type": "code",
        "client_id":    settings.oidc_client_id,
        "redirect_uri": settings.oidc_redirect_uri,
        "scope":        "openid email profile",
        "state":        state,
        "nonce":        nonce,
        "code_challenge":        code_challenge,
        "code_challenge_method": "S256",
    })
    return RedirectResponse(url=disco["authorization_endpoint"] + "?" + qs, status_code=302)


@app.get("/oidc/callback")
async def oidc_callback(code: str, state: str, response: Response):
    if not settings.oidc_issuer:
        raise HTTPException(status_code=503, detail="OIDC not configured")
    import httpx
    disco = await _oidc_discovery()
    async with pool().acquire() as con:
        row = await con.fetchrow(
            "DELETE FROM cabinet_oidc_state WHERE state=$1 RETURNING nonce, code_verifier, return_to",
            state,
        )
    if row is None:
        raise HTTPException(status_code=400, detail="invalid or expired state")
    code_verifier = row["code_verifier"]
    return_to = row["return_to"] or "/cabinet.html"

    import traceback as _tb, logging as _lg
    _log = _lg.getLogger("uvicorn.error")
    try:
        async with httpx.AsyncClient(timeout=20) as cli:
            tok_r = await cli.post(
                disco["token_endpoint"],
                data={
                    "grant_type":    "authorization_code",
                    "code":          code,
                    "redirect_uri":  settings.oidc_redirect_uri,
                    "client_id":     settings.oidc_client_id,
                    "client_secret": settings.oidc_client_secret,
                    "code_verifier": code_verifier,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            _log.warning("OIDC token POST status=%s body=%s", tok_r.status_code, tok_r.text[:500])
            if tok_r.status_code != 200:
                raise HTTPException(status_code=502, detail=f"token exchange failed [{tok_r.status_code}]: {tok_r.text[:500]}")
            tokens = tok_r.json()
            access_token = tokens.get("access_token")
            ui_r = await cli.get(disco["userinfo_endpoint"], headers={"Authorization": f"Bearer {access_token}"})
            _log.warning("OIDC userinfo status=%s body=%s", ui_r.status_code, ui_r.text[:500])
            if ui_r.status_code != 200:
                raise HTTPException(status_code=502, detail=f"userinfo failed [{ui_r.status_code}]: {ui_r.text[:500]}")
            ui = ui_r.json()
    except HTTPException:
        raise
    except Exception as e:
        _log.exception("OIDC callback crashed")
        raise HTTPException(status_code=502, detail=f"oidc callback exception {type(e).__name__}: {str(e)[:300]}")

    sub   = ui.get("sub")
    email = (ui.get("email") or "").lower()
    name  = ui.get("name") or ui.get("preferred_username") or email
    if not sub or not email:
        raise HTTPException(status_code=502, detail="userinfo missing sub/email")

    sid = _secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + _td(days=settings.cabinet_session_days)
    async with pool().acquire() as con:
        urow = await con.fetchrow(
            """
            INSERT INTO cabinet_users (sub, email, display_name, last_login_at)
            VALUES ($1,$2,$3, now())
            ON CONFLICT (sub) DO UPDATE SET
                email = EXCLUDED.email,
                display_name = EXCLUDED.display_name,
                last_login_at = now()
            RETURNING id
            """,
            sub, email, name,
        )
        await con.execute(
            "INSERT INTO cabinet_sessions (id, user_id, expires_at) VALUES ($1,$2,$3)",
            sid, urow["id"], expires,
        )

    resp = RedirectResponse(url=return_to, status_code=302)
    resp.set_cookie(
        key=settings.cabinet_cookie_name, value=sid,
        max_age=settings.cabinet_session_days * 86400,
        httponly=True, secure=True, samesite="lax",
    )
    return resp


async def _current_user(session_cookie: Optional[str]) -> Optional[dict]:
    if not session_cookie:
        return None
    async with pool().acquire() as con:
        row = await con.fetchrow(
            """
            SELECT u.id, u.email, u.display_name
              FROM cabinet_sessions s JOIN cabinet_users u ON u.id = s.user_id
             WHERE s.id = $1 AND s.expires_at > now()
            """,
            session_cookie,
        )
    return dict(row) if row else None


def _require_user(user: Optional[dict]) -> dict:
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user


@app.get("/cabinet/me")
async def cabinet_me(vg_session: Optional[str] = Cookie(default=None)):
    user = await _current_user(vg_session)
    if not user:
        return {"authenticated": False}
    return {"authenticated": True, **user}


@app.post("/cabinet/logout")
async def cabinet_logout(response: Response, vg_session: Optional[str] = Cookie(default=None)):
    if vg_session:
        async with pool().acquire() as con:
            await con.execute("DELETE FROM cabinet_sessions WHERE id=$1", vg_session)
    response.delete_cookie(settings.cabinet_cookie_name)
    return {"ok": True}


# Bookmarks --------------------------------------------------------------

class BookmarkIn(BaseModel):
    url: str = Field(..., min_length=1, max_length=2000)
    title: Optional[str] = Field(default=None, max_length=500)
    note: Optional[str] = Field(default=None, max_length=2000)


@app.get("/cabinet/bookmarks")
async def bookmarks_list(vg_session: Optional[str] = Cookie(default=None)):
    user = _require_user(await _current_user(vg_session))
    async with pool().acquire() as con:
        rows = await con.fetch(
            "SELECT id, url, title, note, created_at FROM cabinet_bookmarks WHERE user_id=$1 ORDER BY created_at DESC",
            user["id"],
        )
    return [dict(r) for r in rows]


@app.post("/cabinet/bookmarks")
async def bookmarks_add(req: BookmarkIn, vg_session: Optional[str] = Cookie(default=None)):
    user = _require_user(await _current_user(vg_session))
    async with pool().acquire() as con:
        row = await con.fetchrow(
            """
            INSERT INTO cabinet_bookmarks (user_id, url, title, note)
            VALUES ($1,$2,$3,$4)
            ON CONFLICT (user_id, url) DO UPDATE SET title=EXCLUDED.title, note=EXCLUDED.note
            RETURNING id, url, title, note, created_at
            """,
            user["id"], req.url, req.title, req.note,
        )
    return dict(row)


@app.delete("/cabinet/bookmarks/{bm_id}")
async def bookmarks_del(bm_id: int, vg_session: Optional[str] = Cookie(default=None)):
    user = _require_user(await _current_user(vg_session))
    async with pool().acquire() as con:
        await con.execute("DELETE FROM cabinet_bookmarks WHERE id=$1 AND user_id=$2", bm_id, user["id"])
    return {"ok": True}


# Saved queries ----------------------------------------------------------

class SavedQueryIn(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    label: Optional[str] = Field(default=None, max_length=100)


@app.get("/cabinet/queries")
async def queries_list(vg_session: Optional[str] = Cookie(default=None)):
    user = _require_user(await _current_user(vg_session))
    async with pool().acquire() as con:
        rows = await con.fetch(
            "SELECT id, query, label, created_at FROM cabinet_saved_queries WHERE user_id=$1 ORDER BY created_at DESC",
            user["id"],
        )
    return [dict(r) for r in rows]


@app.post("/cabinet/queries")
async def queries_add(req: SavedQueryIn, vg_session: Optional[str] = Cookie(default=None)):
    user = _require_user(await _current_user(vg_session))
    async with pool().acquire() as con:
        row = await con.fetchrow(
            """
            INSERT INTO cabinet_saved_queries (user_id, query, label)
            VALUES ($1,$2,$3)
            ON CONFLICT (user_id, query) DO UPDATE SET label=EXCLUDED.label
            RETURNING id, query, label, created_at
            """,
            user["id"], req.query, req.label,
        )
    return dict(row)


@app.delete("/cabinet/queries/{q_id}")
async def queries_del(q_id: int, vg_session: Optional[str] = Cookie(default=None)):
    user = _require_user(await _current_user(vg_session))
    async with pool().acquire() as con:
        await con.execute("DELETE FROM cabinet_saved_queries WHERE id=$1 AND user_id=$2", q_id, user["id"])
    return {"ok": True}


# Subscriptions (subscribe to query — get notified about new results) ----

class SubscriptionIn(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)


@app.get("/cabinet/subscriptions")
async def subs_list(vg_session: Optional[str] = Cookie(default=None)):
    user = _require_user(await _current_user(vg_session))
    async with pool().acquire() as con:
        rows = await con.fetch(
            "SELECT id, query, last_seen_id, last_check, created_at FROM cabinet_subscriptions WHERE user_id=$1 ORDER BY created_at DESC",
            user["id"],
        )
    return [dict(r) for r in rows]


@app.post("/cabinet/subscriptions")
async def subs_add(req: SubscriptionIn, vg_session: Optional[str] = Cookie(default=None)):
    user = _require_user(await _current_user(vg_session))
    async with pool().acquire() as con:
        row = await con.fetchrow(
            """
            INSERT INTO cabinet_subscriptions (user_id, query)
            VALUES ($1,$2)
            ON CONFLICT (user_id, query) DO NOTHING
            RETURNING id, query, last_seen_id, last_check, created_at
            """,
            user["id"], req.query,
        )
        if row is None:
            row = await con.fetchrow(
                "SELECT id, query, last_seen_id, last_check, created_at FROM cabinet_subscriptions WHERE user_id=$1 AND query=$2",
                user["id"], req.query,
            )
    return dict(row)


@app.delete("/cabinet/subscriptions/{s_id}")
async def subs_del(s_id: int, vg_session: Optional[str] = Cookie(default=None)):
    user = _require_user(await _current_user(vg_session))
    async with pool().acquire() as con:
        await con.execute("DELETE FROM cabinet_subscriptions WHERE id=$1 AND user_id=$2", s_id, user["id"])
    return {"ok": True}

# ---------------------------------------------------------------------------
# Subscription worker — runs from cron, finds new results for each
# active subscription and updates last_seen_id.
# ---------------------------------------------------------------------------


@app.post("/cabinet/subscriptions/scan")
async def subs_scan(authorization: Optional[str] = Header(default=None)):
    """Cron-only endpoint (Bearer ADMIN_TOKEN). For every subscription,
    runs a vector search and records new top hits compared to the last
    seen id. Returns a summary list — the cron pipes it to whatever
    notification channel is configured (email/Telegram/etc, future)."""
    _require_admin(authorization)
    summary: list[dict] = []
    async with pool().acquire() as con:
        subs = await con.fetch(
            """SELECT s.id, s.user_id, s.query, s.last_seen_id, u.email, u.display_name
                 FROM cabinet_subscriptions s JOIN cabinet_users u ON u.id = s.user_id"""
        )
    for s in subs:
        qvec = await embed_query(s["query"])
        async with pool().acquire() as con:
            top = await con.fetchrow(
                """SELECT id, url, title, 1 - (embedding <=> $1) AS score
                     FROM pages
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> $1
                    LIMIT 1""",
                qvec,
            )
        if not top:
            continue
        new_top = top["id"]
        is_new = (s["last_seen_id"] != new_top)
        if is_new:
            async with pool().acquire() as con:
                await con.execute(
                    "UPDATE cabinet_subscriptions SET last_seen_id=$1, last_check=now() WHERE id=$2",
                    new_top, s["id"],
                )
            summary.append({
                "subscription_id": s["id"],
                "user_email": s["email"],
                "query": s["query"],
                "new_top_url": top["url"],
                "new_top_title": top["title"],
                "score": float(top["score"]),
            })
        else:
            async with pool().acquire() as con:
                await con.execute(
                    "UPDATE cabinet_subscriptions SET last_check=now() WHERE id=$1",
                    s["id"],
                )
    return {"checked": len(subs), "new_results": len(summary), "items": summary}
