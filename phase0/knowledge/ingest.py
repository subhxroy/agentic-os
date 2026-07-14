import hashlib
import uuid
import os
import json
from typing import Optional
from database import pg_query, pg_execute, pg_execute_returning

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _get_embed_fn():
    """Return local embedding function. Falls back to None if unavailable."""
    try:
        from embeddings.local import embed_text
        return embed_text
    except ImportError:
        return None


def upload_document(user_id: str, filename: str, content: bytes, source_type: str = "upload") -> dict:
    file_hash = hashlib.sha256(content).hexdigest()
    filepath = os.path.join(UPLOAD_DIR, f"{file_hash}_{filename}")
    with open(filepath, "wb") as f:
        f.write(content)

    return pg_execute_returning(
        """INSERT INTO documents (id, user_id, title, source_type, file_path, file_hash, status)
           VALUES (?, ?, ?, ?, ?, ?, 'pending') RETURNING *""",
        (str(uuid.uuid4()), user_id, filename, source_type, filepath, file_hash)
    )

def chunk_text(text: str, chunk_size: int = 512, overlap: int = 50) -> list[str]:
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks

def process_document(doc_id: str, text: str, embed_fn=None):
    """Process document into chunks with local embeddings."""
    if embed_fn is None:
        embed_fn = _get_embed_fn()

    chunks = chunk_text(text)
    for i, chunk_content in enumerate(chunks):
        embedding = embed_fn(chunk_content) if embed_fn else None
        embedding_json = json.dumps(embedding) if embedding else None
        pg_execute(
            """INSERT INTO chunks (id, document_id, chunk_index, content, token_count, embedding)
                VALUES (?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), doc_id, i, chunk_content, len(chunk_content.split()), embedding_json)
        )
    pg_execute(
        "UPDATE documents SET status = 'ready', chunk_count = ?, updated_at = datetime('now') WHERE id = ?",
        (len(chunks), doc_id)
    )

def search_knowledge(user_id: str, query_embedding: list, limit: int = 5) -> list[dict]:
    """Vector search via Python cosine similarity."""
    from database import vector_search
    return vector_search(
        table="chunks c JOIN documents d ON c.document_id = d.id",
        embedding_col="embedding",
        query_embedding=query_embedding,
        where_clause="WHERE d.user_id = ? AND d.status = 'ready' AND c.embedding IS NOT NULL",
        params=(user_id,),
        limit=limit
    )

def get_user_documents(user_id: str) -> list[dict]:
    return pg_query(
        "SELECT id, title, source_type, status, chunk_count, created_at FROM documents WHERE user_id = %s ORDER BY created_at DESC",
        (user_id,)
    )
