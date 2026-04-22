#!/usr/bin/env python3
"""
YACY Vector Reindexer — local PostgreSQL + pgvector
Embeddings via HuggingFace Inference API (intfloat/multilingual-e5-base, 768 dims).

Usage:
  python3 reindex_vectors.py              # only files changed in last commit
  python3 reindex_vectors.py --full       # full reindex of all project files
  python3 reindex_vectors.py --file PATH  # reindex specific file
  python3 reindex_vectors.py --query "пошуковий запит"  # test semantic search
"""

import os
import sys
import re
import subprocess
import time
import argparse
import requests
from pathlib import Path
from typing import Generator

# ── Dependencies ─────────────────────────────────────────────────────────────
try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "psycopg2-binary", "requests",
                    "--break-system-packages", "-q"], check=True)
    import psycopg2
    import psycopg2.extras

# ── Config ────────────────────────────────────────────────────────────────────
PG_DSN     = os.environ.get("YACY_PG_DSN",
             f"dbname=yacy_vectors user={os.environ.get('USER', 'vladyslavnovytskyi')} host=localhost port=5432")
HF_TOKEN   = os.environ.get("HF_TOKEN", "")
HF_MODEL   = "intfloat/multilingual-e5-base"
HF_API_URL = f"https://router.huggingface.co/hf-inference/models/{HF_MODEL}/pipeline/feature-extraction"

MAX_CHARS     = 6000
OVERLAP_CHARS = 800
BATCH_SIZE    = 8

PROJECT_ROOT  = Path(__file__).parent.parent / "yacy_search_server"
INDEXED_EXTS  = {".java", ".html", ".xml", ".js", ".css", ".properties"}
SKIP_DIRS     = {"lib", "libt", ".git", "build", "dist", "node_modules", "langdetect"}


# ── Chunking ──────────────────────────────────────────────────────────────────

def split_by_chars(text: str) -> Generator[tuple[str, int], None, None]:
    if len(text) <= MAX_CHARS:
        yield text, 0
        return
    start, idx = 0, 0
    while start < len(text):
        yield text[start:start + MAX_CHARS], idx
        start += MAX_CHARS - OVERLAP_CHARS
        idx += 1


def chunk_java(content: str) -> list[dict]:
    class_match = re.search(r'\bclass\s+(\w+)', content)
    current_class = class_match.group(1) if class_match else None

    method_pattern = re.compile(
        r'(?=\n\s{0,4}(?:@\w+[^\n]*\n\s{0,4})*'
        r'(?:public|private|protected)\s+(?:static\s+|final\s+|synchronized\s+)*'
        r'\S+\s+\w+\s*\([^)]*\)\s*(?:throws\s+[\w,\s]+)?\s*\{)',
        re.MULTILINE
    )
    splits = [0] + [m.start() for m in method_pattern.finditer(content)] + [len(content)]

    chunks = []
    for i in range(len(splits) - 1):
        segment = content[splits[i]:splits[i+1]]
        if not segment.strip():
            continue
        m = re.search(r'(?:public|private|protected)\s+\S+\s+(\w+)\s*\(', segment)
        method_name = m.group(1) if m else None
        for sub, idx in split_by_chars(segment):
            chunks.append({"class_name": current_class, "method_name": method_name,
                           "content": sub, "chunk_index": len(chunks)})

    if not chunks:
        for sub, idx in split_by_chars(content):
            chunks.append({"class_name": current_class, "method_name": None,
                           "content": sub, "chunk_index": idx})
    return chunks


def chunk_html(content: str) -> list[dict]:
    if len(content) <= MAX_CHARS:
        return [{"class_name": None, "method_name": None, "content": content, "chunk_index": 0}]
    pattern = re.compile(r'(?=<(?:div|section|article|main|header|footer|nav|script|style)\b)', re.IGNORECASE)
    parts = pattern.split(content)
    chunks, acc = [], ""
    for part in parts:
        if len(acc) + len(part) > MAX_CHARS:
            if acc.strip():
                chunks.append({"class_name": None, "method_name": None,
                               "content": acc, "chunk_index": len(chunks)})
            acc = acc[-OVERLAP_CHARS:] + part
        else:
            acc += part
    if acc.strip():
        chunks.append({"class_name": None, "method_name": None,
                       "content": acc, "chunk_index": len(chunks)})
    return chunks or [{"class_name": None, "method_name": None, "content": content, "chunk_index": 0}]


def chunk_file(file_path: Path, content: str) -> list[dict]:
    ext = file_path.suffix.lower()
    if ext == ".java":
        return chunk_java(content)
    elif ext in {".html", ".xml"}:
        return chunk_html(content)
    else:
        return [{"class_name": None, "method_name": None, "content": t, "chunk_index": i}
                for t, i in split_by_chars(content)]


# ── HuggingFace Embeddings ────────────────────────────────────────────────────

def embed_batch(texts: list[str], prefix: str = "passage") -> list[list[float]]:
    """Embed texts via HuggingFace router. Use prefix='query' for search queries."""
    prefixed = [f"{prefix}: {t}" for t in texts]
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}

    for attempt in range(5):
        resp = requests.post(HF_API_URL, headers=headers,
                             json={"inputs": prefixed}, timeout=60)
        if resp.status_code == 200:
            result = resp.json()
            embeddings = []
            for item in result:
                if isinstance(item[0], list):
                    # 3D: mean pool tokens
                    dims = len(item[0])
                    pooled = [sum(tok[d] for tok in item) / len(item) for d in range(dims)]
                    embeddings.append(pooled)
                else:
                    embeddings.append(item)
            return embeddings
        elif resp.status_code in (429, 503):
            wait = 2 ** attempt * (10 if resp.status_code == 429 else 3)
            print(f"  HF {resp.status_code}, waiting {wait}s...")
            time.sleep(wait)
        else:
            raise RuntimeError(f"HF API {resp.status_code}: {resp.text[:200]}")

    raise RuntimeError("Failed after 5 retries")


# ── Git helpers ───────────────────────────────────────────────────────────────

def get_changed_files() -> list[Path]:
    try:
        r = subprocess.run(["git", "diff", "--name-only", "HEAD~1", "HEAD"],
                           capture_output=True, text=True, cwd=PROJECT_ROOT)
        return [PROJECT_ROOT / line for line in r.stdout.strip().splitlines()
                if (PROJECT_ROOT / line).exists()
                and Path(line).suffix in INDEXED_EXTS
                and not any(s in Path(line).parts for s in SKIP_DIRS)]
    except Exception as e:
        print(f"[git] {e}")
        return []


def get_commit_hash() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"],
                           capture_output=True, text=True, cwd=PROJECT_ROOT)
        return r.stdout.strip()[:12]
    except Exception:
        return "unknown"


def get_all_files() -> list[Path]:
    return [f for ext in INDEXED_EXTS
            for f in PROJECT_ROOT.rglob(f"*{ext}")
            if not any(s in f.parts for s in SKIP_DIRS)]


# ── PostgreSQL upsert ─────────────────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(PG_DSN)


def delete_file_vectors(cur, file_path: str):
    cur.execute("DELETE FROM yacy_vectors WHERE file_path = %s", (file_path,))


def upsert_chunks(cur, rows: list[dict]):
    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO yacy_vectors
          (file_path, language, chunk_index, class_name, method_name, content, embedding, commit_hash)
        VALUES %s
        ON CONFLICT (file_path, chunk_index) DO UPDATE SET
          language    = EXCLUDED.language,
          class_name  = EXCLUDED.class_name,
          method_name = EXCLUDED.method_name,
          content     = EXCLUDED.content,
          embedding   = EXCLUDED.embedding,
          commit_hash = EXCLUDED.commit_hash,
          updated_at  = now()
        """,
        [(r["file_path"], r["language"], r["chunk_index"],
          r.get("class_name"), r.get("method_name"), r["content"],
          r["embedding"], r["commit_hash"]) for r in rows],
        template="(%s, %s, %s, %s, %s, %s, %s::vector, %s)"
    )


# ── Search (for testing) ──────────────────────────────────────────────────────

def search(query: str, threshold: float = 0.5, limit: int = 5):
    emb = embed_batch([query], prefix="query")[0]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT file_path, language, class_name, method_name,
               1 - (embedding <=> %s::vector) AS similarity,
               left(content, 200) AS preview
        FROM yacy_vectors
        WHERE 1 - (embedding <=> %s::vector) > %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (emb, emb, threshold, emb, limit)
    )
    rows = cur.fetchall()
    conn.close()
    return rows


# ── Main logic ────────────────────────────────────────────────────────────────

def index_files(files: list[Path], commit_hash: str):
    if not files:
        print("No files to index.")
        return

    print(f"Indexing {len(files)} files (commit {commit_hash})")
    conn = get_conn()
    cur  = conn.cursor()
    total_chunks = 0

    all_rows = []
    for file_path in files:
        try:
            relative = str(file_path.relative_to(PROJECT_ROOT.parent))
            content  = file_path.read_text(encoding="utf-8", errors="ignore")
            if not content.strip():
                continue
            chunks   = chunk_file(file_path, content)
            language = file_path.suffix.lstrip(".")
            delete_file_vectors(cur, relative)
            for chunk in chunks:
                all_rows.append({
                    "file_path":   relative,
                    "language":    language,
                    "chunk_index": chunk["chunk_index"],
                    "class_name":  chunk.get("class_name"),
                    "method_name": chunk.get("method_name"),
                    "content":     chunk["content"],
                    "commit_hash": commit_hash,
                })
            print(f"  {relative} → {len(chunks)} chunks")
        except Exception as e:
            print(f"  ERROR {file_path.name}: {e}")

    if not all_rows:
        conn.close()
        return

    print(f"Embedding {len(all_rows)} chunks (batches of {BATCH_SIZE})...")
    for i in range(0, len(all_rows), BATCH_SIZE):
        batch = all_rows[i:i + BATCH_SIZE]
        embeddings = embed_batch([r["content"] for r in batch])
        for row, emb in zip(batch, embeddings):
            row["embedding"] = emb
        upsert_chunks(cur, batch)
        conn.commit()
        done = min(i + BATCH_SIZE, len(all_rows))
        print(f"  {done}/{len(all_rows)}", end="\r")

    total_chunks = len(all_rows)

    # Rebuild ivfflat index after full reindex for better recall
    cur.execute("SELECT COUNT(*) FROM yacy_vectors")
    count = cur.fetchone()[0]
    if count > 1000:
        print("\nRebuilding vector index...")
        cur.execute("DROP INDEX IF EXISTS yacy_vectors_embedding_idx")
        lists = min(count // 10, 1000)
        cur.execute(f"""
            CREATE INDEX yacy_vectors_embedding_idx
            ON yacy_vectors USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = {lists})
        """)
        conn.commit()

    conn.close()
    print(f"\nDone. {total_chunks} chunks indexed. Total in DB: {count}")


def main():
    parser = argparse.ArgumentParser(description="YACY Vector Reindexer (local PostgreSQL)")
    parser.add_argument("--full",  action="store_true", help="Full reindex of all files")
    parser.add_argument("--file",  type=str,            help="Reindex specific file")
    parser.add_argument("--query", type=str,            help="Test semantic search")
    args = parser.parse_args()

    if args.query:
        if not HF_TOKEN:
            print("ERROR: HF_TOKEN not set in ~/.yacy_env")
            sys.exit(1)
        print(f"Searching: {args.query}\n")
        results = search(args.query)
        if not results:
            print("No results found.")
        for row in results:
            file_path, lang, cls, method, sim, preview = row
            print(f"[{sim:.3f}] {file_path}")
            if cls:   print(f"         class: {cls}" + (f".{method}()" if method else ""))
            print(f"         {preview.strip()[:120]}\n")
        return

    if not HF_TOKEN:
        print("ERROR: HF_TOKEN not set in ~/.yacy_env")
        sys.exit(1)

    commit = get_commit_hash()

    if args.file:
        files = [Path(args.file)]
    elif args.full:
        files = get_all_files()
        print(f"Full reindex: {len(files)} files")
    else:
        files = get_changed_files()
        print(f"Incremental: {len(files)} changed files")

    index_files(files, commit)


if __name__ == "__main__":
    main()
