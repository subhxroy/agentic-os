import os
import re
import sqlite3
import threading
import json
import time
import math
from typing import Optional

# ============================================================
# SQLite + diskcache backend (replaces Postgres + Redis)
# ============================================================

DATA_DIR = os.environ.get("AGENTOS_DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "agentos.db")

_cache = None

def _get_cache():
    """Disk-backed cache replacing Redis."""
    global _cache
    if _cache is None:
        try:
            import diskcache
            _cache = diskcache.Cache(os.path.join(DATA_DIR, "cache"))
        except ImportError:
            # Fallback: in-memory dict (no persistence)
            class _MemCache:
                def __init__(self):
                    self._data = {}
                    self._expires = {}
                def get(self, key, default=None):
                    if key in self._expires and time.time() > self._expires[key]:
                        del self._data[key]
                        del self._expires[key]
                    return self._data.get(key, default)
                def set(self, key, value, expire=None, **kw):
                    self._data[key] = value
                    if expire:
                        self._expires[key] = time.time() + expire
                def delete(self, key):
                    self._data.pop(key, None)
                    self._expires.pop(key, None)
                def incr(self, key, expire=None):
                    val = self._data.get(key, 0) + 1
                    self._data[key] = val
                    if expire:
                        self._expires[key] = time.time() + expire
                    return val
                def ping(self):
                    return True
            _cache = _MemCache()
    return _cache

def get_redis():
    """Return a Redis-compatible interface backed by diskcache."""
    return _get_cache()

def redis_conn():
    return get_redis()


# ============================================================
# SQLite connection (thread-local)
# ============================================================
_local = threading.local()

def _get_conn():
    if not hasattr(_local, 'conn') or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, timeout=30)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
        _local.conn.execute("PRAGMA busy_timeout=5000")
    return _local.conn

def get_pg():
    """Compatibility shim: returns the thread-local sqlite3 connection."""
    return _get_conn()

def put_pg(conn):
    """No-op: SQLite connections are thread-local and persistent."""
    pass


# ============================================================
# SQL adapter: convert Postgres %s placeholders to SQLite ?
# ============================================================

def _adapt_sql(sql: str) -> str:
    """Convert Postgres-style SQL to SQLite-compatible SQL."""
    result = sql

    # Replace %s with ? but not %%s (escaped)
    result = re.sub(r'(?<!%)%s', '?', result)
    result = result.replace('%%', '%')

    # Replace NOW() with datetime('now')
    result = result.replace('NOW()', "datetime('now')")
    result = re.sub(r"to_timestamp\(\?*\)", "datetime('now')", result)

    # Remove ::jsonb and ::vector casts
    result = re.sub(r'::jsonb', '', result)
    result = re.sub(r'::vector', '', result)

    # ILIKE → LIKE (SQLite LIKE is case-insensitive for ASCII by default)
    result = re.sub(r'\bILIKE\b', 'LIKE', result)

    # EXTRACT(EPOCH FROM (completed_at - started_at)) * 1000 → manual calculation
    result = re.sub(
        r"EXTRACT\(EPOCH FROM \((\w+) - (\w+)\)\) \* 1000",
        r"(julianday(\1) - julianday(\2)) * 86400000",
        result
    )

    # metadata->>'key' → json_extract(metadata, '$.key')
    def _jsonb_access(m):
        col, key = m.group(1), m.group(2)
        return f"json_extract({col}, '$.{key}')"
    result = re.sub(r"(\w+)->>'(\w+)'", _jsonb_access, result)

    # arr1 && arr2 (array overlap) → json_each check
    # Replace: mp.tags && ? → mp.tags LIKE '%?%'
    result = re.sub(r'(\w+)\.tags && (\?)', r"\1.tags LIKE '%' || \2 || '%'", result)

    # GIN index syntax removal
    result = result.replace("USING GIN(tags)", "")
    result = result.replace("USING GIN(links)", "")
    result = re.sub(r'USING GIN\([^)]+\)', '', result)

    # HNSW index removal
    result = re.sub(r'USING hnsw \([^)]+\)', '', result)

    # to_tsvector FTS removal
    result = re.sub(r"USING GIN \(to_tsvector\('english', (\w+)\)\)", r'', result)

    # TRUE/FALSE → 1/0 in UPDATE SET and WHERE clauses
    result = re.sub(r'\b=\s*TRUE\b', '= 1', result)
    result = re.sub(r'\b=\s*FALSE\b', '= 0', result)

    # EXCLUDED.column → (SELECT column FROM excluded) for upserts
    # SQLite supports EXCLUDED.* in INSERT ON CONFLICT DO UPDATE

    return result


def _adapt_returning(sql: str) -> tuple[bool, str]:
    """Check if query uses RETURNING. Returns (has_returning, adapted_sql)."""
    match = re.search(r'\bRETURNING\s+(\*|\w+(?:\s*,\s*\w+)*)\b', sql, re.IGNORECASE)
    if match:
        returning_cols = match.group(1)
        adapted = re.sub(r'\s*RETURNING\s+\*\s*$', '', sql, flags=re.IGNORECASE)
        adapted = re.sub(r'\s*RETURNING\s+\w+(?:\s*,\s*\w+)*\s*$', '', adapted, flags=re.IGNORECASE)
        return True, adapted, returning_cols
    return False, sql, ""


# ============================================================
# Query functions (drop-in replacements for pg_query/pg_execute)
# ============================================================

def _convert_row(row):
    """Convert sqlite3.Row to dict."""
    if row is None:
        return None
    return dict(row)

def _convert_rows(rows):
    """Convert list of sqlite3.Row to list of dicts."""
    return [dict(r) for r in rows]


def pg_query(sql: str, params: tuple = (), as_dict: bool = True) -> list:
    adapted = _adapt_sql(sql)
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(adapted, params)
        rows = cur.fetchall()
        if as_dict:
            return _convert_rows(rows)
        return rows
    finally:
        cur.close()


def pg_execute(sql: str, params: tuple = ()):
    adapted = _adapt_sql(sql)
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(adapted, params)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def pg_execute_returning(sql: str, params: tuple = ()) -> Optional[dict]:
    has_returning, adapted, cols = _adapt_returning(sql)
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(adapted, params)
        row_id = cur.lastrowid
        conn.commit()
        if has_returning:
            table = _extract_table_from_insert(adapted)
            if table and row_id:
                cur2 = conn.cursor()
                cur2.execute(f"SELECT * FROM {table} WHERE rowid = ?", (row_id,))
                row = cur2.fetchone()
                cur2.close()
                return _convert_row(row) if row else None
        return None
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def _extract_table_from_insert(sql: str) -> Optional[str]:
    """Extract table name from INSERT INTO statement."""
    match = re.search(r'INSERT\s+INTO\s+(\w+)', sql, re.IGNORECASE)
    return match.group(1) if match else None


# ============================================================
# Vector search helpers (Python cosine similarity)
# ============================================================

def vector_search(table: str, embedding_col: str, query_embedding: list,
                  where_clause: str = "", params: tuple = (),
                  limit: int = 5) -> list[dict]:
    """Perform cosine similarity search in Python when sqlite-vec unavailable."""
    conn = _get_conn()
    sql = f"SELECT *, rowid FROM {table} {where_clause}"
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
    finally:
        cur.close()

    results = []
    for row in rows:
        row_dict = dict(row)
        emb_blob = row_dict.get(embedding_col)
        if emb_blob is None:
            continue
        # Embedding stored as JSON string
        try:
            if isinstance(emb_blob, str):
                emb = json.loads(emb_blob)
            elif isinstance(emb_blob, bytes):
                emb = json.loads(emb_blob.decode())
            else:
                emb = emb_blob
        except (json.JSONDecodeError, TypeError):
            continue
        sim = _cosine_similarity(query_embedding, emb)
        row_dict['similarity'] = sim
        results.append(row_dict)

    results.sort(key=lambda x: x['similarity'], reverse=True)
    return results[:limit]


def _cosine_similarity(a: list, b: list) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
