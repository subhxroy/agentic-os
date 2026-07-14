import uuid
from database import pg_query, pg_execute, pg_execute_returning


def create_app(user_id: str, name: str, description: str = None,
               redirect_uris: list = None, scopes: list = None, org_id: str = None) -> dict:
    app_id = str(uuid.uuid4())
    pg_execute(
        """INSERT INTO apps (id, user_id, org_id, name, description, redirect_uris, scopes)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (app_id, user_id, org_id, name, description, redirect_uris or [],
         scopes or ["read", "write"])
    )
    return get_app(app_id)


def get_app(app_id: str) -> dict:
    rows = pg_query("SELECT * FROM apps WHERE id = %s", (app_id,))
    return rows[0] if rows else None


def list_user_apps(user_id: str) -> list:
    return pg_query("SELECT * FROM apps WHERE user_id = %s ORDER BY created_at DESC", (user_id,))


def update_app(app_id: str, **kwargs) -> dict:
    allowed = {"name", "description", "redirect_uris", "scopes", "status"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return get_app(app_id)
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    pg_execute(f"UPDATE apps SET {set_clause}, updated_at = NOW() WHERE id = %s",
               list(updates.values()) + [app_id])
    return get_app(app_id)


def delete_app(app_id: str) -> bool:
    pg_execute("DELETE FROM apps WHERE id = %s", (app_id,))
    return True


def create_api_key(user_id: str, org_id: str = None, app_id: str = None,
                   name: str = None, scopes: list = None) -> dict:
    import json as _json
    raw_key = f"ao_{uuid.uuid4().hex}"
    import hashlib
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_id = str(uuid.uuid4())
    pg_execute(
        """INSERT INTO api_keys (id, user_id, org_id, app_id, key_hash, name, scopes)
           VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)""",
        (key_id, user_id, org_id, app_id, key_hash, name or f"key_{key_id[:8]}",
         _json.dumps(scopes or ["read", "write"]))
    )
    return {"id": key_id, "key": raw_key, "name": name or f"key_{key_id[:8]}",
            "scopes": scopes or ["read", "write"]}


def verify_api_key(raw_key: str) -> dict:
    import hashlib
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    rows = pg_query(
        """SELECT ak.*, u.id as uid, u.email, u.name
           FROM api_keys ak JOIN users u ON ak.user_id = u.id
           WHERE ak.key_hash = %s AND (ak.expires_at IS NULL OR ak.expires_at > NOW())""",
        (key_hash,)
    )
    if rows:
        pg_execute("UPDATE api_keys SET last_used_at = NOW() WHERE id = %s", (rows[0]["id"],))
    return rows[0] if rows else None


def list_api_keys(user_id: str) -> list:
    return pg_query(
        """SELECT id, name, scopes, app_id, last_used_at, created_at
           FROM api_keys WHERE user_id = %s ORDER BY created_at DESC""",
        (user_id,)
    )


def revoke_api_key(key_id: str) -> bool:
    pg_execute("DELETE FROM api_keys WHERE id = %s", (key_id,))
    return True


def track_api_usage(api_key_id: str, user_id: str, org_id: str,
                    endpoint: str, method: str, status_code: int = None,
                    response_time_ms: int = None, tokens_used: int = 0,
                    model: str = None) -> None:
    pg_execute(
        """INSERT INTO api_usage (id, api_key_id, user_id, org_id, endpoint, method,
           status_code, response_time_ms, tokens_used, model)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (str(uuid.uuid4()), api_key_id, user_id, org_id, endpoint, method,
         status_code, response_time_ms, tokens_used, model)
    )


def get_usage_analytics(user_id: str, days: int = 30) -> dict:
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(days=days)

    total = pg_query(
        "SELECT COUNT(*) as count FROM api_usage WHERE user_id = %s AND created_at > %s",
        (user_id, cutoff)
    )
    by_endpoint = pg_query(
        """SELECT endpoint, method, COUNT(*) as count, AVG(response_time_ms) as avg_ms,
           SUM(tokens_used) as total_tokens
           FROM api_usage WHERE user_id = %s AND created_at > %s
           GROUP BY endpoint, method ORDER BY count DESC LIMIT 20""",
        (user_id, cutoff)
    )
    by_day = pg_query(
        """SELECT DATE(created_at) as day, COUNT(*) as count, SUM(tokens_used) as tokens
           FROM api_usage WHERE user_id = %s AND created_at > %s
           GROUP BY DATE(created_at) ORDER BY day""",
        (user_id, cutoff)
    )
    by_model = pg_query(
        """SELECT model, COUNT(*) as count, SUM(tokens_used) as tokens
           FROM api_usage WHERE user_id = %s AND created_at > %s AND model IS NOT NULL
           GROUP BY model ORDER BY count DESC""",
        (user_id, cutoff)
    )
    return {
        "total_requests": total[0]["count"] if total else 0,
        "by_endpoint": by_endpoint,
        "by_day": by_day,
        "by_model": by_model,
        "period_days": days,
    }


def get_org_usage_analytics(org_id: str, days: int = 30) -> dict:
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(days=days)

    total = pg_query(
        "SELECT COUNT(*) as count FROM api_usage WHERE org_id = %s AND created_at > %s",
        (org_id, cutoff)
    )
    by_user = pg_query(
        """SELECT u.email, COUNT(*) as count, SUM(au.tokens_used) as tokens
           FROM api_usage au JOIN users u ON au.user_id = u.id
           WHERE au.org_id = %s AND au.created_at > %s
           GROUP BY u.email ORDER BY count DESC""",
        (org_id, cutoff)
    )
    by_day = pg_query(
        """SELECT DATE(created_at) as day, COUNT(*) as count, SUM(tokens_used) as tokens
           FROM api_usage WHERE org_id = %s AND created_at > %s
           GROUP BY DATE(created_at) ORDER BY day""",
        (org_id, cutoff)
    )
    return {
        "total_requests": total[0]["count"] if total else 0,
        "by_user": by_user,
        "by_day": by_day,
        "period_days": days,
    }


# ============================================================
# PLUGINS
# ============================================================
def create_plugin(user_id: str, name: str, display_name: str,
                  description: str = None, manifest: dict = None, org_id: str = None) -> dict:
    import json as _json
    plugin_id = str(uuid.uuid4())
    pg_execute(
        """INSERT INTO plugins (id, user_id, name, display_name, description, manifest)
           VALUES (%s, %s, %s, %s, %s, %s::jsonb)""",
        (plugin_id, user_id, name, display_name, description, _json.dumps(manifest or {}))
    )
    return get_plugin(plugin_id)


def get_plugin(plugin_id: str) -> dict:
    rows = pg_query("SELECT * FROM plugins WHERE id = %s", (plugin_id,))
    return rows[0] if rows else None


def get_plugin_by_name(name: str) -> dict:
    rows = pg_query("SELECT * FROM plugins WHERE name = %s", (name,))
    return rows[0] if rows else None


def list_plugins(status: str = "published", limit: int = 50) -> list:
    return pg_query(
        "SELECT * FROM plugins WHERE status = %s ORDER BY installs_count DESC LIMIT %s",
        (status, limit)
    )


def list_user_plugins(user_id: str) -> list:
    return pg_query("SELECT * FROM plugins WHERE user_id = %s ORDER BY created_at DESC", (user_id,))


def update_plugin(plugin_id: str, **kwargs) -> dict:
    import json as _json
    allowed = {"display_name", "description", "version", "manifest", "status"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return get_plugin(plugin_id)
    # Convert manifest dict to JSON string for jsonb column
    if "manifest" in updates:
        updates["manifest"] = _json.dumps(updates["manifest"])
    set_parts = []
    values = []
    for k, v in updates.items():
        if k == "manifest":
            set_parts.append(f"{k} = %s::jsonb")
        else:
            set_parts.append(f"{k} = %s")
        values.append(v)
    pg_execute(f"UPDATE plugins SET {', '.join(set_parts)}, updated_at = NOW() WHERE id = %s",
               values + [plugin_id])
    return get_plugin(plugin_id)


def publish_plugin(plugin_id: str) -> dict:
    return update_plugin(plugin_id, status="published")


def install_plugin(plugin_id: str, user_id: str, org_id: str = None, config: dict = None) -> dict:
    import json as _json
    install_id = str(uuid.uuid4())
    config_json = _json.dumps(config or {})
    pg_execute(
        """INSERT INTO plugin_installs (id, plugin_id, user_id, org_id, config)
           VALUES (%s, %s, %s, %s, %s::jsonb)
           ON CONFLICT (plugin_id, user_id) DO UPDATE SET config = %s::jsonb""",
        (install_id, plugin_id, user_id, org_id, config_json, config_json)
    )
    pg_execute("UPDATE plugins SET installs_count = installs_count + 1 WHERE id = %s", (plugin_id,))
    return {"id": install_id, "plugin_id": plugin_id, "status": "active"}


def uninstall_plugin(plugin_id: str, user_id: str) -> bool:
    pg_execute("DELETE FROM plugin_installs WHERE plugin_id = %s AND user_id = %s", (plugin_id, user_id))
    pg_execute("UPDATE plugins SET installs_count = GREATEST(installs_count - 1, 0) WHERE id = %s", (plugin_id,))
    return True


def list_user_plugin_installs(user_id: str) -> list:
    return pg_query(
        """SELECT pi.*, p.name as plugin_name, p.display_name, p.version
           FROM plugin_installs pi JOIN plugins p ON pi.plugin_id = p.id
           WHERE pi.user_id = %s AND pi.status = 'active'""",
        (user_id,)
    )
