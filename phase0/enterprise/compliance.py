import json
import uuid
import os
import zipfile
from datetime import datetime, timedelta
from typing import Optional
from database import pg_query, pg_execute, pg_execute_returning

EXPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "exports")
os.makedirs(EXPORT_DIR, exist_ok=True)

# ============================================================
# ORG SETTINGS
# ============================================================
def get_org_settings(org_id: str) -> Optional[dict]:
    rows = pg_query("SELECT * FROM org_settings WHERE org_id = %s", (org_id,))
    return rows[0] if rows else None

def upsert_org_settings(org_id: str, settings: dict) -> dict:
    existing = get_org_settings(org_id)
    if existing:
        set_clauses = []
        params = []
        for key, value in settings.items():
            if key in ("ip_allowlist", "sso_config", "mfa_required", "session_duration_hours",
                       "max_sessions_per_user", "conversation_retention_days", "audit_retention_days",
                       "auto_delete_expired", "data_classification", "dpa_agreed", "soc2_enabled",
                       "sso_provider", "scim_enabled"):
                set_clauses.append(f"{key} = %s")
                params.append(json.dumps(value) if isinstance(value, (list, dict)) else value)
        if set_clauses:
            set_clauses.append("updated_at = NOW()")
            params.append(org_id)
            pg_execute(f"UPDATE org_settings SET {', '.join(set_clauses)} WHERE org_id = %s", tuple(params))
    else:
        settings["org_id"] = org_id
        pg_execute(
            """INSERT INTO org_settings (id, org_id, ip_allowlist, mfa_required,
               session_duration_hours, max_sessions_per_user, conversation_retention_days,
               audit_retention_days, auto_delete_expired, data_classification, dpa_agreed,
               soc2_enabled, sso_provider, sso_config, scim_enabled)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (str(uuid.uuid4()), org_id,
             json.dumps(settings.get("ip_allowlist", [])),
             settings.get("mfa_required", False),
             settings.get("session_duration_hours", 24),
             settings.get("max_sessions_per_user", 10),
             settings.get("conversation_retention_days", 90),
             settings.get("audit_retention_days", 365),
             settings.get("auto_delete_expired", False),
             settings.get("data_classification", "internal"),
             settings.get("dpa_agreed", False),
             settings.get("soc2_enabled", False),
             settings.get("sso_provider"),
             json.dumps(settings.get("sso_config", {})),
             settings.get("scim_enabled", False))
        )
    return get_org_settings(org_id)

def check_ip_allowed(org_id: str, ip_address: str) -> bool:
    settings = get_org_settings(org_id)
    if not settings or not settings.get("ip_allowlist"):
        return True  # No restriction = allow all
    import ipaddress
    try:
        client_ip = ipaddress.ip_address(ip_address)
        for cidr in settings["ip_allowlist"]:
            if client_ip in ipaddress.ip_network(cidr, strict=False):
                return True
        return False
    except ValueError:
        return True

# ============================================================
# GDPR DATA EXPORT
# ============================================================
def request_data_export(user_id: str) -> dict:
    return pg_execute_returning(
        """INSERT INTO gdpr_requests (id, user_id, request_type, status)
           VALUES (%s, %s, 'export', 'pending') RETURNING *""",
        (str(uuid.uuid4()), user_id)
    )

def process_data_export(request_id: str) -> Optional[dict]:
    req = pg_query("SELECT * FROM gdpr_requests WHERE id = %s AND status = 'pending'", (request_id,))
    if not req:
        return None
    request = req[0]
    user_id = request["user_id"]

    pg_execute("UPDATE gdpr_requests SET status = 'processing' WHERE id = %s", (request_id,))

    try:
        # Collect all user data
        user = pg_query("SELECT id, email, name, created_at FROM users WHERE id = %s", (user_id,))[0]
        sessions = pg_query("SELECT * FROM sessions WHERE user_id = %s", (user_id,))
        conversations = []
        for s in sessions:
            msgs = pg_query(
                "SELECT role, content, tool_calls, tool_results, created_at FROM conversations WHERE session_id = %s ORDER BY created_at",
                (s["id"],)
            )
            conversations.extend(msgs)
        memories = pg_query("SELECT key, content, memory_type, importance, created_at FROM memories WHERE user_id = %s", (user_id,))
        documents = pg_query("SELECT id, title, source_type, status, created_at FROM documents WHERE user_id = %s", (user_id,))
        feedback_items = pg_query(
            "SELECT f.rating, f.comment, f.created_at FROM feedback f JOIN sessions s ON f.session_id = s.id WHERE s.user_id = %s",
            (user_id,)
        )
        audit = pg_query("SELECT * FROM audit_log WHERE user_id = %s", (user_id,))

        export_data = {
            "export_date": datetime.utcnow().isoformat(),
            "user": user,
            "sessions": [{"id": s["id"], "goal": s["goal"], "state": s["state"],
                          "created_at": str(s["created_at"])} for s in sessions],
            "conversations": [{"role": c["role"], "content": c["content"],
                               "created_at": str(c["created_at"])} for c in conversations],
            "memories": [{"key": m["key"], "content": m["content"], "type": m["memory_type"],
                          "importance": m["importance"]} for m in memories],
            "documents": [{"title": d["title"], "source_type": d["source_type"],
                           "status": d["status"]} for d in documents],
            "feedback": [{"rating": f["rating"], "comment": f["comment"]} for f in feedback_items],
            "audit_log": [{"action": a["action"], "resource_type": a["resource_type"],
                           "created_at": str(a["created_at"])} for a in audit],
        }

        # Write to ZIP
        filename = f"gdpr_export_{user_id[:8]}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
        filepath = os.path.join(EXPORT_DIR, filename)
        with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("export.json", json.dumps(export_data, indent=2, default=str))
            zf.writestr("README.txt", f"GDPR Data Export for user {user_id}\nGenerated: {datetime.utcnow().isoformat()}")

        pg_execute(
            "UPDATE gdpr_requests SET status = 'completed', file_path = %s, completed_at = NOW() WHERE id = %s",
            (filepath, request_id)
        )
        return {"status": "completed", "file": filepath, "record_count": len(conversations) + len(memories)}
    except Exception as e:
        pg_execute(
            "UPDATE gdpr_requests SET status = 'failed' WHERE id = %s",
            (request_id,)
        )
        return {"status": "failed", "error": str(e)}

# ============================================================
# GDPR DATA DELETION (Right to Erasure)
# ============================================================
def request_data_deletion(user_id: str) -> dict:
    return pg_execute_returning(
        """INSERT INTO gdpr_requests (id, user_id, request_type, status)
           VALUES (%s, %s, 'deletion', 'pending') RETURNING *""",
        (str(uuid.uuid4()), user_id)
    )

def process_data_deletion(request_id: str) -> Optional[dict]:
    req = pg_query("SELECT * FROM gdpr_requests WHERE id = %s AND status = 'pending'", (request_id,))
    if not req:
        return None
    request = req[0]
    user_id = request["user_id"]

    pg_execute("UPDATE gdpr_requests SET status = 'processing' WHERE id = %s", (request_id,))

    try:
        # Delete user data (cascade handles most, but be explicit)
        pg_execute("DELETE FROM feedback WHERE user_id = %s", (user_id,))
        pg_execute("DELETE FROM comments WHERE user_id = %s", (user_id,))
        pg_execute("DELETE FROM conversations WHERE session_id IN (SELECT id FROM sessions WHERE user_id = %s)", (user_id,))
        pg_execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
        pg_execute("DELETE FROM memories WHERE user_id = %s", (user_id,))
        pg_execute("DELETE FROM documents WHERE user_id = %s", (user_id,))
        pg_execute("DELETE FROM agent_templates WHERE created_by = %s", (user_id,))
        pg_execute("DELETE FROM api_keys WHERE user_id = %s", (user_id,))
        pg_execute("DELETE FROM org_members WHERE user_id = %s", (user_id,))
        pg_execute("DELETE FROM invitations WHERE invited_by = %s OR email IN (SELECT email FROM users WHERE id = %s)", (user_id, user_id))
        pg_execute("DELETE FROM knowledge_bases WHERE created_by = %s", (user_id,))
        pg_execute("DELETE FROM refresh_tokens WHERE user_id = %s", (user_id,))
        pg_execute("DELETE FROM apps WHERE user_id = %s", (user_id,))
        pg_execute("DELETE FROM plugin_installs WHERE user_id = %s", (user_id,))
        pg_execute("DELETE FROM plugins WHERE user_id = %s", (user_id,))
        pg_execute("DELETE FROM package_reviews WHERE user_id = %s", (user_id,))
        pg_execute("DELETE FROM package_downloads WHERE user_id = %s", (user_id,))
        pg_execute("DELETE FROM revenue_transactions WHERE user_id = %s", (user_id,))
        pg_execute("DELETE FROM developer_payouts WHERE user_id = %s", (user_id,))
        pg_execute("DELETE FROM export_log WHERE user_id = %s", (user_id,))

        # Anonymize user record (don't hard delete for referential integrity)
        pg_execute(
            "UPDATE users SET email = 'deleted_' || id || '@anonymized.local', name = 'Deleted User', password_hash = '' WHERE id = %s",
            (user_id,)
        )

        pg_execute(
            "UPDATE gdpr_requests SET status = 'completed', completed_at = NOW() WHERE id = %s",
            (request_id,)
        )
        return {"status": "completed", "user_id": user_id}
    except Exception as e:
        pg_execute(
            "UPDATE gdpr_requests SET status = 'failed' WHERE id = %s",
            (request_id,)
        )
        return {"status": "failed", "error": str(e)}

# ============================================================
# DATA RETENTION (auto-cleanup)
# ============================================================
def run_retention_cleanup(org_id: str = None) -> dict:
    results = {"conversations_deleted": 0, "audit_deleted": 0, "sessions_deleted": 0}

    if org_id:
        settings = get_org_settings(org_id)
        if not settings:
            return results
        conv_days = settings.get("conversation_retention_days", 90)
        audit_days = settings.get("audit_retention_days", 365)
    else:
        conv_days = 90
        audit_days = 365

    # Delete old conversations
    conv_cutoff = (datetime.utcnow() - timedelta(days=conv_days)).isoformat()
    before = pg_query("SELECT COUNT(*) as cnt FROM conversations WHERE created_at < ?", (conv_cutoff,))
    pg_execute("DELETE FROM conversations WHERE created_at < ?", (conv_cutoff,))
    results["conversations_deleted"] = before[0]["cnt"] if before else 0

    # Delete old audit logs
    audit_cutoff = (datetime.utcnow() - timedelta(days=audit_days)).isoformat()
    before_audit = pg_query("SELECT COUNT(*) as cnt FROM audit_log WHERE created_at < ?", (audit_cutoff,))
    pg_execute("DELETE FROM audit_log WHERE created_at < ?", (audit_cutoff,))
    results["audit_deleted"] = before_audit[0]["cnt"] if before_audit else 0

    return results

# ============================================================
# COMPLIANCE SNAPSHOT
# ============================================================
def generate_compliance_snapshot(org_id: str) -> dict:
    today = datetime.utcnow().date().isoformat()
    cutoff_30d = (datetime.utcnow() - timedelta(days=30)).isoformat()
    total_users = pg_query(
        "SELECT COUNT(*) as cnt FROM org_members WHERE org_id = ?", (org_id,)
    )[0]["cnt"]
    active_users = pg_query(
        """SELECT COUNT(DISTINCT al.user_id) as cnt FROM audit_log al
           JOIN org_members om ON al.user_id = om.user_id
           WHERE om.org_id = ? AND al.created_at > ?""",
        (org_id, cutoff_30d)
    )[0]["cnt"]
    total_sessions = pg_query(
        "SELECT COUNT(*) as cnt FROM sessions s JOIN org_members om ON s.user_id = om.user_id WHERE om.org_id = ?",
        (org_id,)
    )[0]["cnt"]
    total_docs = pg_query(
        """SELECT COUNT(*) as cnt FROM documents d
           JOIN org_members om ON d.user_id = om.user_id WHERE om.org_id = ?""",
        (org_id,)
    )[0]["cnt"]
    audit_count = pg_query(
        "SELECT COUNT(*) as cnt FROM audit_log WHERE org_id = ?", (org_id,)
    )[0]["cnt"]
    gdpr_pending = pg_query(
        """SELECT COUNT(*) as cnt FROM gdpr_requests g
           JOIN users u ON g.user_id = u.id
           JOIN org_members om ON u.id = om.user_id
           WHERE om.org_id = ? AND g.status = 'pending'""",
        (org_id,)
    )[0]["cnt"]

    settings = get_org_settings(org_id)
    data_class = settings.get("data_classification", "internal") if settings else "internal"

    snapshot = pg_execute_returning(
        """INSERT INTO compliance_snapshots
           (id, org_id, snapshot_date, total_users, active_users_30d, total_sessions,
            total_knowledge_docs, audit_log_count, gdpr_requests_pending, data_classification)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (org_id, snapshot_date) DO UPDATE SET
            total_users = excluded.total_users, active_users_30d = excluded.active_users_30d,
            total_sessions = excluded.total_sessions, total_knowledge_docs = excluded.total_knowledge_docs,
            audit_log_count = excluded.audit_log_count, gdpr_requests_pending = excluded.gdpr_requests_pending""",
        (str(uuid.uuid4()), org_id, today, total_users, active_users, total_sessions,
         total_docs, audit_count, gdpr_pending, data_class)
    )
    return snapshot

# ============================================================
# AUDIT LOG EXPORT
# ============================================================
def export_audit_log(org_id: str, format: str = "json", days: int = 30, user_id: str = None) -> dict:
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    logs = pg_query(
        """SELECT al.*, u.email as user_email FROM audit_log al
           LEFT JOIN users u ON al.user_id = u.id
           WHERE al.org_id = ? AND al.created_at > ?
           ORDER BY al.created_at DESC""",
        (org_id, cutoff)
    )

    filename = f"audit_export_{org_id[:8]}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.{format}"
    filepath = os.path.join(EXPORT_DIR, filename)

    if format == "json":
        with open(filepath, "w") as f:
            json.dump(logs, f, indent=2, default=str)
    elif format == "csv":
        import csv
        if logs:
            with open(filepath, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=logs[0].keys())
                writer.writeheader()
                writer.writerows(logs)

    pg_execute(
        "INSERT INTO export_log (id, user_id, org_id, export_type, format, record_count, file_path) VALUES (%s, %s, %s, 'audit', %s, %s, %s)",
        (str(uuid.uuid4()), user_id, org_id, format, len(logs), filepath)
    )
    return {"file": filepath, "record_count": len(logs), "format": format}

# ============================================================
# ADMIN DASHBOARD
# ============================================================
def get_admin_dashboard(org_id: str) -> dict:
    members = pg_query(
        """SELECT u.id, u.email, u.name, om.role, om.joined_at,
                  (SELECT MAX(created_at) FROM audit_log WHERE user_id = u.id) as last_active
           FROM org_members om
           JOIN users u ON om.user_id = u.id
           WHERE om.org_id = ?""",
        (org_id,)
    )
    settings = get_org_settings(org_id)
    recent_audit = get_audit_log(org_id, limit=10)
    cutoff_7d = (datetime.utcnow() - timedelta(days=7)).isoformat()
    usage = pg_query(
        """SELECT al.action, COUNT(*) as count
           FROM audit_log al WHERE al.org_id = ? AND al.created_at > ?
           GROUP BY al.action ORDER BY count DESC""",
        (org_id, cutoff_7d)
    )
    compliance = pg_query(
        "SELECT * FROM compliance_snapshots WHERE org_id = ? ORDER BY snapshot_date DESC LIMIT 1",
        (org_id,)
    )
    gdpr_pending = pg_query(
        """SELECT COUNT(*) as cnt FROM gdpr_requests g
           JOIN users u ON g.user_id = u.id
           JOIN org_members om ON u.id = om.user_id
           WHERE om.org_id = ? AND g.status = 'pending'""",
        (org_id,)
    )[0]["cnt"]

    return {
        "members": members,
        "settings": settings,
        "recent_audit": recent_audit,
        "usage_7d": usage,
        "compliance_snapshot": compliance[0] if compliance else None,
        "gdpr_pending": gdpr_pending,
    }

def get_audit_log(org_id: str, limit: int = 50, offset: int = 0,
                  action_filter: str = None) -> list[dict]:
    if action_filter:
        return pg_query(
            """SELECT al.*, u.email as user_email
               FROM audit_log al LEFT JOIN users u ON al.user_id = u.id
               WHERE al.org_id = %s AND al.action = %s
               ORDER BY al.created_at DESC LIMIT %s OFFSET %s""",
            (org_id, action_filter, limit, offset)
        )
    return pg_query(
        """SELECT al.*, u.email as user_email
           FROM audit_log al LEFT JOIN users u ON al.user_id = u.id
           WHERE al.org_id = %s
           ORDER BY al.created_at DESC LIMIT %s OFFSET %s""",
        (org_id, limit, offset)
    )
