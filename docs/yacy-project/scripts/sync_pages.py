#!/usr/bin/env python3
"""
YACY Solr → vector_service sync.

Pulls pages indexed by YaCy's Solr and pushes them to the vector service's
/index endpoint. Designed to run from cron nightly (low-traffic hours)
against the local vector service.

Two modes:
  --since ISO8601    explicit since-timestamp (UTC)
  (default)          use state file: docs/yacy-project/.sync_pages.state

State file holds the `load_date_dt` of the most recent successfully-indexed
page so the next run picks up from there. Crash-safe: we only advance the
state after a full batch succeeds.

Requirements:
  pip install httpx

Example:
  export YACY_SOLR_URL=http://localhost:8090/solr/collection1
  export YACY_SOLR_AUTH=admin:yourpass
  export VECTOR_SERVICE_URL=http://127.0.0.1:8001
  python3 sync_pages.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

SOLR_URL = os.environ.get("YACY_SOLR_URL", "http://localhost:8090/solr/collection1")
SOLR_AUTH = os.environ.get("YACY_SOLR_AUTH", "")  # "user:pass" or empty
VECTOR_URL = os.environ.get("VECTOR_SERVICE_URL", "http://127.0.0.1:8001")

STATE_FILE = Path(__file__).resolve().parent.parent / ".sync_pages.state"

BATCH_SIZE = 200
SOLR_FIELDS = "id,sku,title,text_t,host_s,last_modified,load_date_dt,language_s"
# Cap what we send to the vector service. It also caps server-side, but
# trimming here saves JSON-transport bytes on very large pages.
MAX_SUMMARY_CHARS = 6000


def _auth() -> tuple[str, str] | None:
    if not SOLR_AUTH or ":" not in SOLR_AUTH:
        return None
    u, _, p = SOLR_AUTH.partition(":")
    return (u, p)


def _read_state() -> str:
    if STATE_FILE.exists():
        return STATE_FILE.read_text().strip()
    return "1970-01-01T00:00:00Z"


def _write_state(ts: str) -> None:
    STATE_FILE.write_text(ts)


def _iter_solr_batches(since: str, client: httpx.Client):
    """Yield Solr hits ordered by load_date_dt asc. Cursor-mark pagination."""
    cursor = "*"
    fq = f"load_date_dt:[{since} TO *]"
    while True:
        params = {
            "q": "*:*",
            "fq": fq,
            "fl": SOLR_FIELDS,
            "sort": "load_date_dt asc,id asc",  # cursor requires unique tiebreaker
            "rows": str(BATCH_SIZE),
            "wt": "json",
            "cursorMark": cursor,
        }
        r = client.get(f"{SOLR_URL}/select", params=params, auth=_auth(), timeout=60.0)
        r.raise_for_status()
        data = r.json()
        docs = data.get("response", {}).get("docs", [])
        next_cursor = data.get("nextCursorMark")
        if not docs:
            return
        yield docs
        if next_cursor == cursor:
            return
        cursor = next_cursor


def _build_index_payload(doc: dict) -> dict | None:
    doc_id = doc.get("id")
    url = doc.get("sku")
    if not doc_id or not url:
        return None
    text = doc.get("text_t") or ""
    if isinstance(text, list):
        text = " ".join(text)
    text = text.strip()[:MAX_SUMMARY_CHARS]
    if not text:
        # No visible text — skip rather than indexing an all-title blank.
        # YaCy has plenty of those (redirects, thin pages) and they poison the
        # vector space.
        return None
    # Several Solr fields come back as single-item lists (multivalued schema).
    # Unwrap to the first non-empty value so the vector_service Pydantic
    # schema accepts them.
    title = doc.get("title")
    if isinstance(title, list):
        title = title[0] if title else None
    host = doc.get("host_s")
    if isinstance(host, list):
        host = host[0] if host else None
    lang = doc.get("language_s")
    if isinstance(lang, list):
        lang = lang[0] if lang else None
    last_modified = doc.get("last_modified")
    if isinstance(last_modified, list):
        last_modified = last_modified[0] if last_modified else None
    return {
        "id": doc_id,
        "url": url,
        "title": title or None,
        "summary": text,
        "host": host or None,
        "lang": lang or None,
        "last_modified": last_modified or None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="ISO8601 UTC (overrides state file)")
    ap.add_argument("--dry-run", action="store_true", help="don't POST, just count")
    args = ap.parse_args()

    since = args.since or _read_state()
    print(f"[sync] SOLR={SOLR_URL}  VECTOR={VECTOR_URL}  since={since}")

    total = 0
    sent = 0
    skipped_empty = 0
    embedded = 0
    reused = 0
    errors = 0
    last_load_date: str | None = None
    t0 = time.time()

    with httpx.Client() as client:
        for batch in _iter_solr_batches(since, client):
            for doc in batch:
                total += 1
                payload = _build_index_payload(doc)
                if payload is None:
                    skipped_empty += 1
                    continue
                if args.dry_run:
                    sent += 1
                else:
                    try:
                        r = client.post(f"{VECTOR_URL}/index", json=payload, timeout=60.0)
                        r.raise_for_status()
                        sent += 1
                        if r.json().get("embedded"):
                            embedded += 1
                        else:
                            reused += 1
                    except Exception as e:
                        errors += 1
                        print(f"[sync] ERROR indexing {payload['id']}: {e}", file=sys.stderr)
                        continue
                ld = doc.get("load_date_dt")
                if ld:
                    last_load_date = ld
            if last_load_date and not args.dry_run:
                _write_state(last_load_date)

    dt = time.time() - t0
    print(
        f"[sync] done in {dt:.1f}s  total={total} sent={sent} "
        f"embedded={embedded} reused={reused} skipped_empty={skipped_empty} errors={errors}"
    )
    if last_load_date and not args.dry_run:
        print(f"[sync] state advanced to {last_load_date}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
