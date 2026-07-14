import uuid
import secrets
from datetime import datetime, timedelta
from typing import Optional
from database import pg_query, pg_execute, pg_execute_returning

# ============================================================
# INVITATIONS
# ============================================================
def create_invitation(org_id: str, email: str, invited_by: str, role: str = "member") -> dict:
    token = secrets.token_urlsafe(32)
    return pg_execute_returning(
        """INSERT INTO invitations (id, org_id, email, role, invited_by, token)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING *""",
        (str(uuid.uuid4()), org_id, email, role, invited_by, token)
    )

def accept_invitation(token: str, user_id: str) -> Optional[dict]:
    invite = pg_query(
        "SELECT * FROM invitations WHERE token = %s AND status = 'pending' AND expires_at > NOW()",
        (token,)
    )
    if not invite:
        return None
    inv = invite[0]
    # Add user to org
    from auth.jwt_auth import add_org_member
    member = add_org_member(inv["org_id"], user_id, inv["role"])
    # Mark invitation accepted
    pg_execute(
        "UPDATE invitations SET status = 'accepted', accepted_at = NOW() WHERE id = %s",
        (inv["id"],)
    )
    return {"org_id": inv["org_id"], "role": inv["role"], "member": member}

def get_org_invitations(org_id: str) -> list[dict]:
    return pg_query(
        """SELECT i.*, u.email as invited_by_email
           FROM invitations i
           JOIN users u ON i.invited_by = u.id
           WHERE i.org_id = %s AND i.status = 'pending'
           ORDER BY i.created_at DESC""",
        (org_id,)
    )

def get_pending_invitations_for_email(email: str) -> list[dict]:
    return pg_query(
        """SELECT i.*, o.name as org_name
           FROM invitations i
           JOIN organizations o ON i.org_id = o.id
           WHERE i.email = %s AND i.status = 'pending' AND i.expires_at > NOW()""",
        (email,)
    )

# ============================================================
# AUDIT LOG
# ============================================================
def log_audit(org_id: str, user_id: str, action: str,
              resource_type: str = None, resource_id: str = None,
              details: dict = None, ip_address: str = None):
    pg_execute(
        """INSERT INTO audit_log (id, org_id, user_id, action, resource_type, resource_id, details, ip_address)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (str(uuid.uuid4()), org_id, user_id, action,
         resource_type, resource_id,
         json.dumps(details) if details else "{}",
         ip_address)
    )

def get_audit_log(org_id: str, limit: int = 50, offset: int = 0,
                  action_filter: str = None) -> list[dict]:
    if action_filter:
        return pg_query(
            """SELECT al.*, u.email as user_email
               FROM audit_log al
               LEFT JOIN users u ON al.user_id = u.id
               WHERE al.org_id = %s AND al.action = %s
               ORDER BY al.created_at DESC LIMIT %s OFFSET %s""",
            (org_id, action_filter, limit, offset)
        )
    return pg_query(
        """SELECT al.*, u.email as user_email
           FROM audit_log al
           LEFT JOIN users u ON al.user_id = u.id
           WHERE al.org_id = %s
           ORDER BY al.created_at DESC LIMIT %s OFFSET %s""",
        (org_id, limit, offset)
    )

import json

# ============================================================
# SHARED KNOWLEDGE BASES
# ============================================================
def create_knowledge_base(org_id: str, name: str, user_id: str,
                          description: str = None) -> dict:
    return pg_execute_returning(
        """INSERT INTO knowledge_bases (id, org_id, name, description, created_by)
           VALUES (%s, %s, %s, %s, %s) RETURNING *""",
        (str(uuid.uuid4()), org_id, name, description, user_id)
    )

def get_org_knowledge_bases(org_id: str) -> list[dict]:
    return pg_query(
        """SELECT kb.*, u.email as created_by_email,
                  (SELECT COUNT(*) FROM documents d WHERE d.kb_id = kb.id) as doc_count
           FROM knowledge_bases kb
           JOIN users u ON kb.created_by = u.id
           WHERE kb.org_id = %s
           ORDER BY kb.created_at DESC""",
        (org_id,)
    )

def add_document_to_kb(doc_id: str, kb_id: str):
    pg_execute(
        "UPDATE documents SET kb_id = %s, updated_at = NOW() WHERE id = %s",
        (kb_id, doc_id)
    )

def get_kb_documents(kb_id: str) -> list[dict]:
    return pg_query(
        """SELECT d.id, d.title, d.source_type, d.status, d.chunk_count, d.created_at
           FROM documents d WHERE d.kb_id = %s ORDER BY d.created_at DESC""",
        (kb_id,)
    )

def search_kb(kb_id: str, query_embedding: list, limit: int = 5) -> list[dict]:
    return pg_query(
        """SELECT c.content, c.chunk_index, d.title,
                   1 - (c.embedding <=> %s::vector) AS similarity
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE d.kb_id = %s AND d.status = 'ready' AND c.embedding IS NOT NULL
            ORDER BY c.embedding <=> %s::vector LIMIT %s""",
        (json.dumps(query_embedding), kb_id, json.dumps(query_embedding), limit)
    )

# ============================================================
# AGENT TEMPLATES
# ============================================================
def create_template(created_by: str, name: str, description: str = None,
                    system_prompt: str = None, tools: list = None,
                    model_config: dict = None, tags: list = None,
                    visibility: str = "private", org_id: str = None) -> dict:
    return pg_execute_returning(
        """INSERT INTO agent_templates
           (id, org_id, created_by, name, description, system_prompt, tools, model_config, tags, visibility)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
        (str(uuid.uuid4()), org_id, created_by, name, description,
         system_prompt, json.dumps(tools or []), json.dumps(model_config or {}),
         json.dumps(tags or []), visibility)
    )

def get_template(template_id: str) -> Optional[dict]:
    rows = pg_query("SELECT * FROM agent_templates WHERE id = %s", (template_id,))
    return rows[0] if rows else None

def fork_template(original_id: str, forked_by: str, new_name: str = None) -> dict:
    original = get_template(original_id)
    if not original:
        return None
    # Create fork
    forked = create_template(
        created_by=forked_by,
        name=new_name or f"{original['name']} (fork)",
        description=original["description"],
        system_prompt=original["system_prompt"],
        tools=original["tools"],
        model_config=original["model_config"],
        tags=original["tags"],
        visibility="private",
        org_id=original["org_id"],
    )
    # Track fork lineage
    pg_execute(
        "INSERT INTO template_forks (id, original_id, forked_id, forked_by) VALUES (%s, %s, %s, %s)",
        (str(uuid.uuid4()), original_id, forked["id"], forked_by)
    )
    # Increment fork count
    pg_execute(
        "UPDATE agent_templates SET fork_count = fork_count + 1 WHERE id = %s",
        (original_id,)
    )
    return forked

def get_org_templates(org_id: str) -> list[dict]:
    return pg_query(
        """SELECT t.*, u.email as created_by_email
           FROM agent_templates t
           JOIN users u ON t.created_by = u.id
           WHERE t.org_id = %s
           ORDER BY t.created_at DESC""",
        (org_id,)
    )

def get_public_templates(limit: int = 20) -> list[dict]:
    return pg_query(
        """SELECT t.*, u.email as created_by_email, o.name as org_name
           FROM agent_templates t
           JOIN users u ON t.created_by = u.id
           LEFT JOIN organizations o ON t.org_id = o.id
           WHERE t.visibility = 'public'
           ORDER BY t.fork_count DESC, t.created_at DESC LIMIT %s""",
        (limit,)
    )

# ============================================================
# COMMENTS & FEEDBACK
# ============================================================
def add_comment(session_id: str, user_id: str, content: str,
                parent_id: str = None, comment_type: str = "comment") -> dict:
    return pg_execute_returning(
        """INSERT INTO comments (id, session_id, user_id, parent_id, content, comment_type)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING *""",
        (str(uuid.uuid4()), session_id, user_id, parent_id, content, comment_type)
    )

def get_session_comments(session_id: str) -> list[dict]:
    return pg_query(
        """SELECT c.*, u.email as user_email, u.name as user_name
           FROM comments c
           JOIN users u ON c.user_id = u.id
           WHERE c.session_id = %s
           ORDER BY c.created_at ASC""",
        (session_id,)
    )

def add_feedback(session_id: str, user_id: str, rating: int,
                 message_id: str = None, comment: str = None) -> dict:
    return pg_execute_returning(
        """INSERT INTO feedback (id, session_id, message_id, user_id, rating, comment)
           VALUES (%s, %s, %s, %s, %s, %s)
           ON CONFLICT (session_id, message_id, user_id)
           DO UPDATE SET rating = EXCLUDED.rating, comment = EXCLUDED.comment
           RETURNING *""",
        (str(uuid.uuid4()), session_id, message_id, user_id, rating, comment)
    )

def get_session_feedback(session_id: str) -> list[dict]:
    return pg_query(
        """SELECT f.*, u.email as user_email
           FROM feedback f
           JOIN users u ON f.user_id = u.id
           WHERE f.session_id = %s
           ORDER BY f.created_at DESC""",
        (session_id,)
    )
