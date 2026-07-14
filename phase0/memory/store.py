import json
import uuid
from datetime import datetime, timezone
from typing import Optional
from database import pg_query, pg_execute, pg_execute_returning, get_redis

# ============================================================
# SESSIONS
# ============================================================
def create_session(user_id: str, goal: str = None) -> dict:
    return pg_execute_returning(
        "INSERT INTO sessions (id, user_id, goal) VALUES (%s, %s, %s) RETURNING *",
        (str(uuid.uuid4()), user_id, goal)
    )

def update_session(session_id: str, state: str = None, goal: str = None):
    updates, params = [], []
    if state:
        updates.append("state = %s")
        params.append(state)
    if goal:
        updates.append("goal = %s")
        params.append(goal)
    updates.append("updated_at = NOW()")
    params.append(session_id)
    pg_execute(f"UPDATE sessions SET {', '.join(updates)} WHERE id = %s", tuple(params))

# ============================================================
# CONVERSATIONS (short-term memory)
# ============================================================
def save_message(session_id: str, role: str, content: str,
                 tool_calls: Optional[list] = None, tool_results: Optional[list] = None):
    pg_execute(
        "INSERT INTO conversations (session_id, role, content, tool_calls, tool_results) VALUES (%s, %s, %s, %s, %s)",
        (session_id, role, content,
         json.dumps(tool_calls) if tool_calls else None,
         json.dumps(tool_results) if tool_results else None)
    )

def get_conversation_history(session_id: str, limit: int = 50) -> list[dict]:
    return pg_query(
        "SELECT role, content, tool_calls, tool_results FROM conversations WHERE session_id = %s ORDER BY created_at ASC LIMIT %s",
        (session_id, limit)
    )

# ============================================================
# WORKING MEMORY (diskcache-backed — current session state)
# ============================================================
def set_working_memory(session_id: str, key: str, value: any, ttl: int = 86400):
    r = get_redis()
    r.set(f"session:{session_id}:{key}", json.dumps(value), expire=ttl)

def get_working_memory(session_id: str, key: str) -> Optional[any]:
    r = get_redis()
    val = r.get(f"session:{session_id}:{key}")
    return json.loads(val) if val else None

def clear_working_memory(session_id: str):
    r = get_redis()
    for k in ["current_input", "state", "goal"]:
        r.delete(f"session:{session_id}:{k}")

# ============================================================
# LONG-TERM MEMORY (PostgreSQL with vector search)
# ============================================================
def remember(user_id: str, key: str, content: str, memory_type: str = "key_value",
             importance: float = 0.5, embedding: list = None):
    pg_execute(
        """INSERT INTO memories (id, user_id, memory_type, key, content, importance, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (user_id, key) DO UPDATE
            SET content = excluded.content, importance = excluded.importance,
                updated_at = datetime('now'), last_accessed_at = datetime('now')""",
        (str(uuid.uuid4()), user_id, memory_type, key, content, importance,
         json.dumps(embedding) if embedding else None)
    )

def recall(user_id: str, key: str) -> Optional[str]:
    # SQLite doesn't support UPDATE ... RETURNING in older versions
    # Do it in two steps
    pg_execute(
        "UPDATE memories SET access_count = access_count + 1, last_accessed_at = datetime('now') WHERE user_id = ? AND key = ?",
        (user_id, key)
    )
    rows = pg_query(
        "SELECT content FROM memories WHERE user_id = ? AND key = ?",
        (user_id, key)
    )
    return rows[0]["content"] if rows else None

def get_all_memories(user_id: str, limit: int = 100) -> list[dict]:
    return pg_query(
        "SELECT key, content, importance, memory_type, created_at, updated_at FROM memories WHERE user_id = %s ORDER BY importance DESC LIMIT %s",
        (user_id, limit)
    )

def search_memories(user_id: str, query_embedding: list, limit: int = 10) -> list[dict]:
    """Vector search via Python cosine similarity (no pgvector needed)."""
    from database import vector_search
    return vector_search(
        table="memories",
        embedding_col="embedding",
        query_embedding=query_embedding,
        where_clause="WHERE user_id = ? AND embedding IS NOT NULL",
        params=(user_id,),
        limit=limit
    )

# ============================================================
# USER MANAGEMENT
# ============================================================
def create_user(email: str, password_hash: str, name: str = None) -> dict:
    return pg_execute_returning(
        "INSERT INTO users (id, email, password_hash, name) VALUES (%s, %s, %s, %s) RETURNING *",
        (str(uuid.uuid4()), email, password_hash, name)
    )

def get_user_by_email(email: str) -> Optional[dict]:
    rows = pg_query("SELECT * FROM users WHERE email = %s", (email,))
    return rows[0] if rows else None

def get_user_by_id(user_id: str) -> Optional[dict]:
    rows = pg_query("SELECT * FROM users WHERE id = %s", (user_id,))
    return rows[0] if rows else None
