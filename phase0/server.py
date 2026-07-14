import os
import sys
import uuid
import time
from flask import Flask, request, jsonify, send_from_directory, g
from flask_cors import CORS
from flask_socketio import SocketIO, emit

from database import pg_query, pg_execute, pg_execute_returning, get_pg, put_pg, redis_conn
from auth.jwt_auth import (
    create_token, create_refresh_token, hash_password, verify_password,
    require_auth, require_role,
    create_org, add_org_member, get_user_orgs, get_org_members, is_org_member
)
from memory.store import (
    create_user, get_user_by_email, get_user_by_id,
    create_session, save_message, get_conversation_history,
    get_all_memories, set_working_memory
)
from knowledge.ingest import upload_document, process_document, get_user_documents
from agent.loop import AgentLoop
from agent.planner import PlanningEngine

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

agent = AgentLoop()
agent.set_socketio(socketio)
planner = PlanningEngine()

# ============================================================
# GLOBAL JSON ERROR HANDLER
# ============================================================
@app.errorhandler(Exception)
def handle_exception(e):
    if hasattr(e, "code") and hasattr(e, "description"):
        return jsonify({"error": e.description}), e.code
    return jsonify({"error": "Internal server error", "type": type(e).__name__}), 500

# ============================================================
# RATE LIMITER (Redis-backed, falls back to in-memory)
# ============================================================
class RateLimiter:
    def __init__(self):
        self._memory = {}
        self._use_redis = False
        try:
            self._r = redis_conn()
            self._r.ping()
            self._use_redis = True
        except Exception:
            pass

    def check(self, key: str, max_requests: int, window_sec: int) -> bool:
        now = time.time()
        if self._use_redis:
            pipe = self._r.pipeline()
            pipe.incr(key)
            pipe.expire(key, window_sec)
            count, _ = pipe.execute()
            return int(count) <= max_requests
        window_key = f"{key}:{int(now / window_sec)}"
        hits = self._memory.get(window_key, 0)
        if hits >= max_requests:
            return False
        self._memory[window_key] = hits + 1
        return True

rate_limiter = RateLimiter()

def rate_limit(max_requests: int = 60, window_sec: int = 60):
    def decorator(f):
        from functools import wraps
        @wraps(f)
        def decorated(*args, **kwargs):
            key = f"ratelimit:{request.remote_addr}:{request.path}"
            if not rate_limiter.check(key, max_requests, window_sec):
                return jsonify({"error": "Rate limit exceeded"}), 429
            return f(*args, **kwargs)
        return decorated
    return decorator

# ============================================================
# AUTH (JWT-based)
# ============================================================
@app.route("/api/auth/register", methods=["POST"])
@rate_limit(max_requests=5, window_sec=60)
def register():
    from collaboration.team import log_audit
    data = request.json
    email = data.get("email")
    password = data.get("password")
    name = data.get("name")
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    if get_user_by_email(email):
        return jsonify({"error": "Email already registered"}), 409
    password_hash = hash_password(password)
    user = create_user(email, password_hash, name)
    log_audit(None, user["id"], "user.registered",
              resource_type="user", resource_id=user["id"],
              details={"email": email}, ip_address=request.remote_addr)
    # Auto-accept any pending invitations
    from collaboration.team import get_pending_invitations_for_email, accept_invitation
    pending = get_pending_invitations_for_email(email)
    org_id = None
    for inv in pending:
        result = accept_invitation(inv["token"], user["id"])
        if result and not org_id:
            org_id = result["org_id"]
    token = create_token(user["id"], org_id=org_id)
    refresh_token = create_refresh_token(user["id"])
    return jsonify({
        "user": {"id": user["id"], "email": user["email"], "name": user["name"]},
        "token": token,
        "refresh_token": refresh_token,
        "org_id": org_id,
    })

@app.route("/api/auth/login", methods=["POST"])
@rate_limit(max_requests=10, window_sec=60)
def login():
    from collaboration.team import log_audit
    data = request.json
    user = get_user_by_email(data.get("email"))
    if not user or not verify_password(data["password"], user["password_hash"]):
        return jsonify({"error": "Invalid credentials"}), 401
    log_audit(None, user["id"], "user.login",
              resource_type="user", resource_id=user["id"],
              ip_address=request.remote_addr)
    # Get user's primary org (if any)
    orgs = get_user_orgs(user["id"])
    org_id = orgs[0]["id"] if orgs else None
    role = orgs[0].get("role", "member") if orgs else "member"
    token = create_token(user["id"], org_id=org_id, role=role)
    refresh_token = create_refresh_token(user["id"])
    return jsonify({
        "user": {"id": user["id"], "email": user["email"], "name": user["name"]},
        "token": token,
        "refresh_token": refresh_token,
        "org_id": org_id,
    })

@app.route("/api/auth/refresh", methods=["POST"])
@rate_limit(max_requests=5, window_sec=60)
def refresh_token():
    from auth.jwt_auth import create_refresh_token, create_token, rotate_refresh_token
    data = request.json
    old_refresh = data.get("refresh_token")
    user_id = data.get("user_id")
    if not old_refresh or not user_id:
        return jsonify({"error": "refresh_token and user_id required"}), 400
    new_refresh = rotate_refresh_token(old_refresh, user_id)
    if not new_refresh:
        return jsonify({"error": "Invalid or expired refresh token"}), 401
    orgs = get_user_orgs(user_id)
    org_id = orgs[0]["id"] if orgs else None
    role = orgs[0].get("role", "member") if orgs else "member"
    token = create_token(user_id, org_id=org_id, role=role)
    return jsonify({"token": token, "refresh_token": new_refresh})

@app.route("/api/auth/me", methods=["GET"])
@require_auth
def get_me():
    user = get_user_by_id(g.user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    orgs = get_user_orgs(g.user_id)
    return jsonify({
        "user": {"id": user["id"], "email": user["email"], "name": user["name"]},
        "orgs": orgs,
        "current_org_id": g.org_id,
        "role": g.role,
    })

# ============================================================
# ORGANIZATIONS
# ============================================================
@app.route("/api/orgs", methods=["POST"])
@require_auth
def new_org():
    data = request.json
    org = create_org(data["name"], g.user_id)
    return jsonify(org)

@app.route("/api/orgs/<org_id>/members", methods=["GET"])
@require_auth
def list_members(org_id):
    if not is_org_member(org_id, g.user_id):
        return jsonify({"error": "Not a member of this org"}), 403
    return jsonify(get_org_members(org_id))

@app.route("/api/orgs/<org_id>/members", methods=["POST"])
@require_auth
@require_role("owner", "admin")
def add_member(org_id):
    data = request.json
    member = add_org_member(org_id, data["user_id"], data.get("role", "member"))
    return jsonify(member)

# ============================================================
# SESSIONS (protected)
# ============================================================
@app.route("/api/sessions", methods=["POST"])
@require_auth
def new_session():
    data = request.json
    session = create_session(g.user_id, data.get("goal"))
    return jsonify(session)

@app.route("/api/sessions/<session_id>/messages", methods=["GET"])
@require_auth
def get_messages(session_id):
    rows = pg_query("SELECT user_id FROM sessions WHERE id = %s", (session_id,))
    if not rows or rows[0]["user_id"] != g.user_id:
        return jsonify({"error": "Session not found"}), 404
    history = get_conversation_history(session_id, limit=100)
    return jsonify(history)

@app.route("/api/sessions/<session_id>/working-memory", methods=["GET"])
@require_auth
def get_session_working_memory(session_id):
    import json
    rows = pg_query("SELECT user_id FROM sessions WHERE id = ?", (session_id,))
    if not rows or rows[0]["user_id"] != g.user_id:
        return jsonify({"error": "Session not found"}), 404
    r = redis_conn()
    # diskcache doesn't have hgetall — use get with a dict
    all_data = {}
    for key in ["current_input", "state", "goal"]:
        val = r.get(f"session:{session_id}:{key}")
        if val is not None:
            try:
                all_data[key] = json.loads(val)
            except Exception:
                all_data[key] = val
    return jsonify(all_data)

# ============================================================
# CHAT (protected)
# ============================================================
@app.route("/api/chat", methods=["POST"])
@require_auth
@rate_limit(max_requests=30, window_sec=60)
def chat():
    data = request.json
    session_id = data["session_id"]
    message = data["message"]
    tier = data.get("tier", "cost_optimized")

    rows = pg_query("SELECT user_id FROM sessions WHERE id = %s", (session_id,))
    if not rows or rows[0]["user_id"] != g.user_id:
        return jsonify({"error": "Session not found"}), 404

    socketio.emit("thinking", {"session_id": session_id}, namespace="/")

    try:
        response = agent.run(session_id, g.user_id, message, tier=tier)
    except Exception as e:
        error_msg = f"Agent error: {str(e)}"
        socketio.emit("error", {"session_id": session_id, "error": error_msg}, namespace="/")
        return jsonify({"error": error_msg}), 500

    socketio.emit("response", {"session_id": session_id, "response": response}, namespace="/")
    return jsonify({"response": response})

@app.route("/api/chat/confirm", methods=["POST"])
@require_auth
def chat_confirm():
    data = request.json
    session_id = data["session_id"]
    tool_name = data["tool_name"]
    args = data.get("args", {})

    from tools.registry import confirm_tool
    result = confirm_tool(tool_name, args)

    socketio.emit("tool_result", {
        "session_id": session_id,
        "tool_name": tool_name,
        "result": result,
    }, namespace="/")

    return jsonify({"result": result})

# ============================================================
# MEMORY (protected)
# ============================================================
@app.route("/api/memories", methods=["GET"])
@require_auth
def memories():
    mems = get_all_memories(g.user_id)
    return jsonify(mems)

@app.route("/api/memories", methods=["POST"])
@require_auth
def add_memory():
    data = request.json
    from memory.store import remember
    remember(g.user_id, data["key"], data["content"], importance=data.get("importance", 0.5))
    return jsonify({"ok": True})

# ============================================================
# OBSIDIAN BRAIN (Personal Knowledge Graph)
# ============================================================
@app.route("/api/brain/notes", methods=["GET"])
@require_auth
def brain_list_notes():
    from brain.notes import list_notes
    tag = request.args.get("tag")
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    notes = list_notes(g.user_id, tag=tag, limit=limit, offset=offset)
    return jsonify(notes)

@app.route("/api/brain/notes", methods=["POST"])
@require_auth
@rate_limit(max_requests=30, window_sec=60)
def brain_create_note():
    from brain.notes import create_note
    data = request.json
    if not data.get("title"):
        return jsonify({"error": "Title required"}), 400
    note = create_note(
        user_id=g.user_id, title=data["title"],
        content=data.get("content", ""), tags=data.get("tags"),
        org_id=g.org_id
    )
    return jsonify(note), 201

@app.route("/api/brain/notes/<note_id>", methods=["GET"])
@require_auth
def brain_get_note(note_id):
    from brain.notes import get_note
    note = get_note(note_id)
    if not note or note["user_id"] != g.user_id:
        return jsonify({"error": "Note not found"}), 404
    return jsonify(note)

@app.route("/api/brain/notes/<note_id>", methods=["PUT"])
@require_auth
def brain_update_note(note_id):
    from brain.notes import update_note
    data = request.json
    note = update_note(note_id, g.user_id,
                       title=data.get("title"), content=data.get("content"),
                       tags=data.get("tags"))
    if not note:
        return jsonify({"error": "Note not found"}), 404
    return jsonify(note)

@app.route("/api/brain/notes/<note_id>", methods=["DELETE"])
@require_auth
def brain_delete_note(note_id):
    from brain.notes import delete_note
    delete_note(note_id, g.user_id)
    return jsonify({"ok": True})

@app.route("/api/brain/search", methods=["GET"])
@require_auth
def brain_search():
    from brain.notes import search_notes
    q = request.args.get("q", "")
    if not q or len(q) < 2:
        return jsonify([])
    results = search_notes(g.user_id, q)
    return jsonify(results)

@app.route("/api/brain/graph", methods=["GET"])
@require_auth
def brain_graph():
    from brain.notes import get_graph_data
    data = get_graph_data(g.user_id, org_id=g.org_id)
    return jsonify(data)

@app.route("/api/brain/notes/<note_id>/backlinks", methods=["GET"])
@require_auth
def brain_backlinks(note_id):
    from brain.notes import get_backlinks
    links = get_backlinks(note_id)
    return jsonify(links)

# ============================================================
# INVITATIONS
# ============================================================
@app.route("/api/orgs/<org_id>/invitations", methods=["POST"])
@require_auth
@require_role("owner", "admin")
def invite_member(org_id):
    from collaboration.team import create_invitation, log_audit
    data = request.json
    invite = create_invitation(org_id, data["email"], g.user_id, data.get("role", "member"))
    log_audit(org_id, g.user_id, "org.member_invited",
              resource_type="invitation", resource_id=invite["id"],
              details={"email": data["email"], "role": data.get("role", "member")},
              ip_address=request.remote_addr)
    return jsonify(invite)

@app.route("/api/orgs/<org_id>/invitations", methods=["GET"])
@require_auth
def list_invitations(org_id):
    from collaboration.team import get_org_invitations
    return jsonify(get_org_invitations(org_id))

@app.route("/api/invitations/accept/<token>", methods=["POST"])
@require_auth
def accept_invite(token):
    from collaboration.team import accept_invitation, log_audit
    result = accept_invitation(token, g.user_id)
    if not result:
        return jsonify({"error": "Invalid or expired invitation"}), 404
    log_audit(result["org_id"], g.user_id, "org.member_joined",
              resource_type="org", resource_id=result["org_id"],
              ip_address=request.remote_addr)
    return jsonify(result)

@app.route("/api/invitations/pending", methods=["GET"])
@require_auth
def my_pending_invites():
    from collaboration.team import get_pending_invitations_for_email
    user = get_user_by_id(g.user_id)
    return jsonify(get_pending_invitations_for_email(user["email"]))

# ============================================================
# AUDIT LOG
# ============================================================
@app.route("/api/orgs/<org_id>/audit", methods=["GET"])
@require_auth
def audit_log(org_id):
    from collaboration.team import get_audit_log
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    action = request.args.get("action")
    return jsonify(get_audit_log(org_id, limit, offset, action))

# ============================================================
# SHARED KNOWLEDGE BASES
# ============================================================
@app.route("/api/orgs/<org_id>/knowledge-bases", methods=["POST"])
@require_auth
def create_kb(org_id):
    from collaboration.team import create_knowledge_base, log_audit
    data = request.json
    kb = create_knowledge_base(org_id, data["name"], g.user_id, data.get("description"))
    log_audit(org_id, g.user_id, "knowledge.base_created",
              resource_type="knowledge_base", resource_id=kb["id"],
              details={"name": data["name"]})
    return jsonify(kb)

@app.route("/api/orgs/<org_id>/knowledge-bases", methods=["GET"])
@require_auth
def list_kbs(org_id):
    from collaboration.team import get_org_knowledge_bases
    return jsonify(get_org_knowledge_bases(org_id))

@app.route("/api/knowledge-bases/<kb_id>/documents", methods=["POST"])
@require_auth
def add_doc_to_kb(kb_id):
    from collaboration.team import add_document_to_kb
    data = request.json
    add_document_to_kb(data["document_id"], kb_id)
    return jsonify({"ok": True})

@app.route("/api/knowledge-bases/<kb_id>/documents", methods=["GET"])
@require_auth
def list_kb_docs(kb_id):
    from collaboration.team import get_kb_documents
    return jsonify(get_kb_documents(kb_id))

# ============================================================
# AGENT TEMPLATES
# ============================================================
@app.route("/api/templates", methods=["POST"])
@require_auth
def create_tmpl():
    from collaboration.team import create_template
    data = request.json
    tmpl = create_template(
        created_by=g.user_id,
        name=data["name"],
        description=data.get("description"),
        system_prompt=data.get("system_prompt"),
        tools=data.get("tools"),
        model_config=data.get("model_config"),
        tags=data.get("tags"),
        visibility=data.get("visibility", "private"),
        org_id=data.get("org_id", g.org_id),
    )
    return jsonify(tmpl)

@app.route("/api/templates/<template_id>", methods=["GET"])
@require_auth
def get_tmpl(template_id):
    from collaboration.team import get_template
    tmpl = get_template(template_id)
    if not tmpl:
        return jsonify({"error": "Template not found"}), 404
    return jsonify(tmpl)

@app.route("/api/templates/<template_id>/fork", methods=["POST"])
@require_auth
def fork_tmpl(template_id):
    from collaboration.team import fork_template
    data = request.json or {}
    forked = fork_template(template_id, g.user_id, data.get("name"))
    if not forked:
        return jsonify({"error": "Template not found"}), 404
    return jsonify(forked)

@app.route("/api/orgs/<org_id>/templates", methods=["GET"])
@require_auth
def list_org_tmpls(org_id):
    from collaboration.team import get_org_templates
    return jsonify(get_org_templates(org_id))

@app.route("/api/templates/public", methods=["GET"])
@require_auth
def list_public_tmpls():
    from collaboration.team import get_public_templates
    return jsonify(get_public_templates())

# ============================================================
# COMMENTS & FEEDBACK
# ============================================================
@app.route("/api/sessions/<session_id>/comments", methods=["POST"])
@require_auth
def post_comment(session_id):
    from collaboration.team import add_comment, log_audit
    data = request.json
    comment = add_comment(session_id, g.user_id, data["content"],
                          parent_id=data.get("parent_id"),
                          comment_type=data.get("comment_type", "comment"))
    if g.org_id:
        log_audit(g.org_id, g.user_id, "session.commented",
                  resource_type="session", resource_id=session_id)
    return jsonify(comment)

@app.route("/api/sessions/<session_id>/comments", methods=["GET"])
@require_auth
def get_comments(session_id):
    from collaboration.team import get_session_comments
    return jsonify(get_session_comments(session_id))

@app.route("/api/sessions/<session_id>/feedback", methods=["POST"])
@require_auth
def post_feedback(session_id):
    from collaboration.team import add_feedback
    data = request.json
    fb = add_feedback(session_id, g.user_id, data["rating"],
                      message_id=data.get("message_id"),
                      comment=data.get("comment"))
    return jsonify(fb)

@app.route("/api/sessions/<session_id>/feedback", methods=["GET"])
@require_auth
def get_feedback(session_id):
    from collaboration.team import get_session_feedback
    return jsonify(get_session_feedback(session_id))

# ============================================================
# ENTERPRISE: ORG SETTINGS
# ============================================================
@app.route("/api/orgs/<org_id>/settings", methods=["GET"])
@require_auth
@require_role("owner", "admin")
def get_settings(org_id):
    from enterprise.compliance import get_org_settings
    settings = get_org_settings(org_id)
    return jsonify(settings or {})

@app.route("/api/orgs/<org_id>/settings", methods=["PUT"])
@require_auth
@require_role("owner", "admin")
def update_settings(org_id):
    from enterprise.compliance import upsert_org_settings
    from collaboration.team import log_audit
    data = request.json
    settings = upsert_org_settings(org_id, data)
    log_audit(org_id, g.user_id, "org.settings_updated",
              resource_type="org", resource_id=org_id,
              details={"keys": list(data.keys())})
    return jsonify(settings)

# ============================================================
# ENTERPRISE: GDPR
# ============================================================
@app.route("/api/gdpr/export", methods=["POST"])
@require_auth
def gdpr_export():
    from enterprise.compliance import request_data_export, process_data_export
    req = request_data_export(g.user_id)
    result = process_data_export(req["id"])
    return jsonify(result or {"status": "pending"})

@app.route("/api/gdpr/delete", methods=["POST"])
@require_auth
def gdpr_delete():
    from enterprise.compliance import request_data_deletion
    req = request_data_deletion(g.user_id)
    return jsonify({"status": "pending", "request_id": req["id"]})

@app.route("/api/gdpr/requests", methods=["GET"])
@require_auth
def gdpr_requests():
    from database import pg_query
    requests = pg_query(
        "SELECT id, request_type, status, created_at, completed_at FROM gdpr_requests WHERE user_id = %s ORDER BY created_at DESC",
        (g.user_id,)
    )
    return jsonify(requests)

# ============================================================
# ENTERPRISE: AUDIT EXPORT
# ============================================================
@app.route("/api/orgs/<org_id>/audit/export", methods=["GET"])
@require_auth
@require_role("owner", "admin")
def export_audit(org_id):
    from enterprise.compliance import export_audit_log
    fmt = request.args.get("format", "json")
    days = request.args.get("days", 30, type=int)
    result = export_audit_log(org_id, format=fmt, days=days, user_id=g.user_id)
    return jsonify(result)

# ============================================================
# ENTERPRISE: COMPLIANCE
# ============================================================
@app.route("/api/orgs/<org_id>/compliance/snapshot", methods=["POST"])
@require_auth
@require_role("owner", "admin")
def compliance_snapshot(org_id):
    from enterprise.compliance import generate_compliance_snapshot
    snapshot = generate_compliance_snapshot(org_id)
    return jsonify(snapshot)

@app.route("/api/orgs/<org_id>/compliance/snapshot", methods=["GET"])
@require_auth
@require_role("owner", "admin")
def get_compliance_snapshot(org_id):
    from database import pg_query
    snapshots = pg_query(
        "SELECT * FROM compliance_snapshots WHERE org_id = %s ORDER BY snapshot_date DESC LIMIT 30",
        (org_id,)
    )
    return jsonify(snapshots)

# ============================================================
# ENTERPRISE: ADMIN DASHBOARD
# ============================================================
@app.route("/api/orgs/<org_id>/admin/dashboard", methods=["GET"])
@require_auth
@require_role("owner", "admin")
def admin_dashboard(org_id):
    from enterprise.compliance import get_admin_dashboard
    return jsonify(get_admin_dashboard(org_id))

# ============================================================
# ENTERPRISE: RATE LIMIT CONFIG
# ============================================================
@app.route("/api/orgs/<org_id>/rate-limits", methods=["GET"])
@require_auth
@require_role("owner", "admin")
def get_rate_limits(org_id):
    from database import pg_query
    rows = pg_query("SELECT * FROM rate_limit_configs WHERE org_id = %s", (org_id,))
    return jsonify(rows[0] if rows else {"requests_per_minute": 60, "requests_per_hour": 1000})

@app.route("/api/orgs/<org_id>/rate-limits", methods=["PUT"])
@require_auth
@require_role("owner", "admin")
def update_rate_limits(org_id):
    from database import pg_execute, pg_execute_returning
    import json
    data = request.json
    existing = pg_query("SELECT id FROM rate_limit_configs WHERE org_id = %s", (org_id,))
    if existing:
        pg_execute(
            """UPDATE rate_limit_configs SET requests_per_minute = %s, requests_per_hour = %s,
               requests_per_day = %s, tokens_per_day = %s, updated_at = NOW() WHERE org_id = %s""",
            (data.get("requests_per_minute", 60), data.get("requests_per_hour", 1000),
             data.get("requests_per_day", 10000), data.get("tokens_per_day", 1000000), org_id)
        )
    else:
        pg_execute(
            """INSERT INTO rate_limit_configs (id, org_id, requests_per_minute, requests_per_hour, requests_per_day, tokens_per_day)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (str(uuid.uuid4()), org_id, data.get("requests_per_minute", 60),
             data.get("requests_per_hour", 1000), data.get("requests_per_day", 10000),
             data.get("tokens_per_day", 1000000))
        )
    return jsonify({"ok": True})

# ============================================================
# KNOWLEDGE (protected)
# ============================================================
@app.route("/api/documents", methods=["GET"])
@require_auth
def list_documents():
    docs = get_user_documents(g.user_id)
    return jsonify(docs)

@app.route("/api/documents/upload", methods=["POST"])
@require_auth
def upload():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file"}), 400
    file_bytes = file.read()
    doc = upload_document(g.user_id, file.filename, file_bytes)
    text = file_bytes.decode("utf-8", errors="ignore") if doc["source_type"] == "upload" else ""
    process_document(doc["id"], text)
    return jsonify(doc)

# ============================================================
# PLANNING
# ============================================================
@app.route("/api/plan", methods=["POST"])
def plan():
    data = request.json
    from tools.registry import TOOL_REGISTRY
    plan = planner.generate_plan(data["goal"], list(TOOL_REGISTRY.keys()))
    return jsonify(plan)

# ============================================================
# MODEL ROUTER STATS
# ============================================================
@app.route("/api/usage", methods=["GET"])
def usage_stats():
    return jsonify(agent.router.get_usage_stats())

# ============================================================
# DEVELOPER ECOSYSTEM (Phase 5)
# ============================================================
@app.route("/api/developer/apps", methods=["GET"])
@require_auth
def list_apps():
    from developer.apps import list_user_apps
    return jsonify(list_user_apps(g.user_id))

@app.route("/api/developer/apps", methods=["POST"])
@require_auth
def create_app():
    from developer.apps import create_app as _create_app
    from collaboration.team import log_audit
    data = request.json
    app = _create_app(
        user_id=g.user_id, name=data["name"],
        description=data.get("description"),
        redirect_uris=data.get("redirect_uris"),
        scopes=data.get("scopes"),
        org_id=g.org_id
    )
    log_audit(g.org_id, g.user_id, "app.created",
              resource_type="app", resource_id=app["id"],
              details={"name": app["name"]}, ip_address=request.remote_addr)
    return jsonify(app), 201

@app.route("/api/developer/apps/<app_id>", methods=["GET"])
@require_auth
def get_app(app_id):
    from developer.apps import get_app
    return jsonify(get_app(app_id))

@app.route("/api/developer/apps/<app_id>", methods=["PUT"])
@require_auth
def update_app(app_id):
    from developer.apps import update_app
    return jsonify(update_app(app_id, **request.json))

@app.route("/api/developer/apps/<app_id>", methods=["DELETE"])
@require_auth
def delete_app(app_id):
    from developer.apps import delete_app
    delete_app(app_id)
    return jsonify({"ok": True})

@app.route("/api/developer/keys", methods=["GET"])
@require_auth
def list_keys():
    from developer.apps import list_api_keys
    return jsonify(list_api_keys(g.user_id))

@app.route("/api/developer/keys", methods=["POST"])
@require_auth
def create_key():
    from developer.apps import create_api_key
    from collaboration.team import log_audit
    data = request.json or {}
    result = create_api_key(
        user_id=g.user_id, org_id=g.org_id,
        app_id=data.get("app_id"), name=data.get("name"),
        scopes=data.get("scopes")
    )
    log_audit(g.org_id, g.user_id, "api_key.created",
              resource_type="api_key", resource_id=result["id"],
              details={"name": result["name"]}, ip_address=request.remote_addr)
    return jsonify(result), 201

@app.route("/api/developer/keys/<key_id>", methods=["DELETE"])
@require_auth
def revoke_key(key_id):
    from developer.apps import revoke_api_key
    revoke_api_key(key_id)
    return jsonify({"ok": True})

@app.route("/api/developer/usage", methods=["GET"])
@require_auth
def developer_usage():
    from developer.apps import get_usage_analytics
    days = request.args.get("days", 30, type=int)
    return jsonify(get_usage_analytics(g.user_id, days))

@app.route("/api/developer/usage/org", methods=["GET"])
@require_auth
@require_role("admin")
def org_usage():
    from developer.apps import get_org_usage_analytics
    days = request.args.get("days", 30, type=int)
    return jsonify(get_org_usage_analytics(g.org_id, days))

@app.route("/api/developer/plugins", methods=["GET"])
def list_plugins():
    from developer.apps import list_plugins
    status = request.args.get("status", "published")
    return jsonify(list_plugins(status=status))

@app.route("/api/developer/plugins", methods=["POST"])
@require_auth
def create_plugin():
    from developer.apps import create_plugin as _create_plugin
    from collaboration.team import log_audit
    data = request.json
    plugin = _create_plugin(
        user_id=g.user_id, name=data["name"], display_name=data["display_name"],
        description=data.get("description"), manifest=data.get("manifest")
    )
    log_audit(g.org_id, g.user_id, "plugin.created",
              resource_type="plugin", resource_id=plugin["id"],
              details={"name": plugin["name"]}, ip_address=request.remote_addr)
    return jsonify(plugin), 201

@app.route("/api/developer/plugins/<plugin_id>/publish", methods=["POST"])
@require_auth
def publish_plugin(plugin_id):
    from developer.apps import publish_plugin
    plugin = publish_plugin(plugin_id)
    return jsonify(plugin)

@app.route("/api/developer/plugins/<plugin_id>/install", methods=["POST"])
@require_auth
def install_plugin(plugin_id):
    from developer.apps import install_plugin
    data = request.json or {}
    result = install_plugin(plugin_id, g.user_id, g.org_id, config=data.get("config"))
    return jsonify(result), 201

@app.route("/api/developer/plugins/installed", methods=["GET"])
@require_auth
def installed_plugins():
    from developer.apps import list_user_plugin_installs
    return jsonify(list_user_plugin_installs(g.user_id))

# ============================================================
# MARKETPLACE (Phase 6)
# ============================================================
@app.route("/api/marketplace", methods=["GET"])
def marketplace_search():
    from marketplace.packages import search_packages
    query = request.args.get("q")
    category = request.args.get("category")
    sort = request.args.get("sort", "rating")
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    return jsonify(search_packages(query=query, category=category, sort=sort,
                                   limit=limit, offset=offset))

@app.route("/api/marketplace/stats", methods=["GET"])
def marketplace_stats():
    from marketplace.packages import get_marketplace_stats
    return jsonify(get_marketplace_stats())

@app.route("/api/marketplace/packages", methods=["POST"])
@require_auth
def create_marketplace_package():
    from marketplace.packages import create_package
    from collaboration.team import log_audit
    data = request.json
    pkg = create_package(
        publisher_id=g.user_id, name=data["name"], display_name=data["display_name"],
        description=data.get("description"), long_description=data.get("long_description"),
        category=data.get("category", "general"), tags=data.get("tags"),
        icon_url=data.get("icon_url"), license=data.get("license", "MIT")
    )
    log_audit(g.org_id, g.user_id, "package.created",
              resource_type="package", resource_id=pkg["id"],
              details={"name": pkg["name"]}, ip_address=request.remote_addr)
    return jsonify(pkg), 201

@app.route("/api/marketplace/packages/<pkg_id>", methods=["GET"])
def get_marketplace_package(pkg_id):
    from marketplace.packages import get_package, list_versions, list_reviews
    pkg = get_package(pkg_id)
    if not pkg:
        return jsonify({"error": "Package not found"}), 404
    pkg["versions"] = list_versions(pkg_id)
    pkg["reviews"] = list_reviews(pkg_id)
    return jsonify(pkg)

@app.route("/api/marketplace/packages/<pkg_id>", methods=["PUT"])
@require_auth
def update_marketplace_package(pkg_id):
    from marketplace.packages import update_package
    return jsonify(update_package(pkg_id, **request.json))

@app.route("/api/marketplace/packages/<pkg_id>/submit", methods=["POST"])
@require_auth
def submit_package(pkg_id):
    from marketplace.packages import submit_for_review, create_scan
    pkg = submit_for_review(pkg_id)
    create_scan(pkg_id, "security")
    create_scan(pkg_id, "sandbox")
    return jsonify(pkg)

@app.route("/api/marketplace/packages/<pkg_id>/approve", methods=["POST"])
@require_auth
@require_role("admin")
def approve_package(pkg_id):
    from marketplace.packages import approve_package
    data = request.json or {}
    pkg = approve_package(pkg_id, g.user_id, notes=data.get("notes"))
    log_audit(g.org_id, g.user_id, "package.approved",
              resource_type="package", resource_id=pkg_id, ip_address=request.remote_addr)
    return jsonify(pkg)

@app.route("/api/marketplace/packages/<pkg_id>/reject", methods=["POST"])
@require_auth
@require_role("admin")
def reject_package(pkg_id):
    from marketplace.packages import reject_package
    data = request.json or {}
    pkg = reject_package(pkg_id, g.user_id, notes=data.get("notes"))
    log_audit(g.org_id, g.user_id, "package.rejected",
              resource_type="package", resource_id=pkg_id,
              details={"reason": data.get("notes")}, ip_address=request.remote_addr)
    return jsonify(pkg)

@app.route("/api/marketplace/packages/<pkg_id>/versions", methods=["POST"])
@require_auth
def create_package_version(pkg_id):
    from marketplace.packages import create_version
    data = request.json
    ver = create_version(
        package_id=pkg_id, version=data["version"],
        manifest=data.get("manifest"), changelog=data.get("changelog"),
        code_path=data.get("code_path"),
        file_size_bytes=data.get("file_size_bytes", 0),
        checksum=data.get("checksum")
    )
    return jsonify(ver), 201

@app.route("/api/marketplace/packages/<pkg_id>/versions", methods=["GET"])
def list_package_versions(pkg_id):
    from marketplace.packages import list_versions
    return jsonify(list_versions(pkg_id))

@app.route("/api/marketplace/packages/<pkg_id>/reviews", methods=["POST"])
@require_auth
def create_package_review(pkg_id):
    from marketplace.packages import create_review
    data = request.json
    review = create_review(pkg_id, g.user_id, rating=data["rating"],
                           title=data.get("title"), content=data.get("content"))
    return jsonify(review), 201

@app.route("/api/marketplace/packages/<pkg_id>/reviews", methods=["GET"])
def list_package_reviews(pkg_id):
    from marketplace.packages import list_reviews
    return jsonify(list_reviews(pkg_id))

@app.route("/api/marketplace/packages/<pkg_id>/download", methods=["POST"])
@require_auth
def download_package(pkg_id):
    from marketplace.packages import record_download, get_latest_version
    ver = get_latest_version(pkg_id)
    record_download(pkg_id, g.user_id, g.org_id,
                    version_id=ver["id"] if ver else None,
                    ip_address=request.remote_addr)
    return jsonify({"ok": True, "version": ver["version"] if ver else None})

@app.route("/api/marketplace/packages/<pkg_id>/analytics", methods=["GET"])
@require_auth
def package_analytics(pkg_id):
    from marketplace.packages import get_download_analytics
    days = request.args.get("days", 30, type=int)
    return jsonify(get_download_analytics(pkg_id, days))

@app.route("/api/marketplace/packages/<pkg_id>/pricing", methods=["POST"])
@require_auth
def set_package_pricing(pkg_id):
    from marketplace.packages import set_pricing
    data = request.json
    pricing = set_pricing(pkg_id, price_type=data.get("price_type", "free"),
                          price_cents=data.get("price_cents", 0),
                          currency=data.get("currency", "USD"),
                          trial_days=data.get("trial_days", 0),
                          subscription_interval=data.get("subscription_interval"))
    return jsonify(pricing)

@app.route("/api/marketplace/packages/<pkg_id>/pricing", methods=["GET"])
def get_package_pricing(pkg_id):
    from marketplace.packages import get_pricing
    return jsonify(get_pricing(pkg_id) or {"price_type": "free", "price_cents": 0})

@app.route("/api/marketplace/my-packages", methods=["GET"])
@require_auth
def my_marketplace_packages():
    from marketplace.packages import list_publisher_packages
    return jsonify(list_publisher_packages(g.user_id))

@app.route("/api/marketplace/revenue", methods=["GET"])
@require_auth
def my_revenue():
    from marketplace.packages import get_developer_revenue
    days = request.args.get("days", 30, type=int)
    return jsonify(get_developer_revenue(g.user_id, days))

@app.route("/api/marketplace/payouts", methods=["POST"])
@require_auth
def request_payout():
    from marketplace.packages import request_payout as _request_payout
    data = request.json
    payout = _request_payout(g.user_id, data["amount_cents"],
                             period_days=data.get("period_days", 30))
    return jsonify(payout), 201

@app.route("/api/marketplace/payouts", methods=["GET"])
@require_auth
def my_payouts():
    from marketplace.packages import list_payouts
    return jsonify(list_payouts(g.user_id))

# ============================================================
# PHASE 7: LARGE-SCALE AGENTOS
# ============================================================
@app.route("/api/kg/entities", methods=["POST"])
@require_auth
def create_kg_entity():
    from scale.knowledge_graph import create_entity
    data = request.json
    entity = create_entity(g.org_id, data["entity_type"], data["name"],
                           description=data.get("description"),
                           properties=data.get("properties"),
                           user_id=g.user_id)
    return jsonify(entity), 201

@app.route("/api/kg/entities", methods=["GET"])
@require_auth
def list_kg_entities():
    from scale.knowledge_graph import search_entities
    query = request.args.get("q")
    entity_type = request.args.get("type")
    return jsonify(search_entities(g.org_id, query=query, entity_type=entity_type))

@app.route("/api/kg/entities/<entity_id>", methods=["GET"])
@require_auth
def get_kg_entity(entity_id):
    from scale.knowledge_graph import get_entity
    return jsonify(get_entity(entity_id))

@app.route("/api/kg/entities/<entity_id>", methods=["PUT"])
@require_auth
def update_kg_entity(entity_id):
    from scale.knowledge_graph import update_entity
    return jsonify(update_entity(entity_id, **request.json))

@app.route("/api/kg/entities/<entity_id>", methods=["DELETE"])
@require_auth
def delete_kg_entity(entity_id):
    from scale.knowledge_graph import delete_entity
    delete_entity(entity_id)
    return jsonify({"ok": True})

@app.route("/api/kg/entities/<entity_id>/neighbors", methods=["GET"])
@require_auth
def kg_neighbors(entity_id):
    from scale.knowledge_graph import get_entity_neighbors
    direction = request.args.get("direction", "both")
    rel_type = request.args.get("rel_type")
    return jsonify(get_entity_neighbors(entity_id, direction=direction, rel_type=rel_type))

@app.route("/api/kg/relationships", methods=["POST"])
@require_auth
def create_kg_relationship():
    from scale.knowledge_graph import create_relationship
    data = request.json
    rel = create_relationship(data["source_id"], data["target_id"],
                              data["relationship_type"],
                              weight=data.get("weight", 1.0),
                              properties=data.get("properties"))
    return jsonify(rel), 201

@app.route("/api/kg/traverse", methods=["POST"])
@require_auth
def kg_traverse():
    from scale.knowledge_graph import traverse_bfs
    data = request.json
    return jsonify(traverse_bfs(data["start_id"], max_depth=data.get("max_depth", 3)))

@app.route("/api/kg/path", methods=["POST"])
@require_auth
def kg_path():
    from scale.knowledge_graph import find_path
    data = request.json
    path = find_path(data["source_id"], data["target_id"])
    return jsonify({"path": path, "length": len(path)})

@app.route("/api/kg/stats", methods=["GET"])
@require_auth
def kg_stats():
    from scale.knowledge_graph import get_graph_stats
    return jsonify(get_graph_stats(g.org_id))

@app.route("/api/kg/snapshot", methods=["POST"])
@require_auth
def kg_snapshot():
    from scale.knowledge_graph import create_snapshot
    return jsonify(create_snapshot(g.org_id)), 201

@app.route("/api/scheduler/tasks", methods=["POST"])
@require_auth
def create_scheduler_task():
    from scale.scheduler import create_task
    data = request.json
    task = create_task(g.org_id, data["task_type"], payload=data.get("payload"),
                       priority=data.get("priority", 5), user_id=g.user_id)
    return jsonify(task), 201

@app.route("/api/scheduler/tasks", methods=["GET"])
@require_auth
def list_scheduler_tasks():
    from scale.scheduler import list_tasks
    status = request.args.get("status")
    task_type = request.args.get("type")
    return jsonify(list_tasks(org_id=g.org_id, status=status, task_type=task_type))

@app.route("/api/scheduler/tasks/<task_id>", methods=["GET"])
@require_auth
def get_scheduler_task(task_id):
    from scale.scheduler import get_task
    return jsonify(get_task(task_id))

@app.route("/api/scheduler/tasks/<task_id>/cancel", methods=["POST"])
@require_auth
def cancel_scheduler_task(task_id):
    from scale.scheduler import cancel_task
    return jsonify(cancel_task(task_id))

@app.route("/api/scheduler/stats", methods=["GET"])
@require_auth
def scheduler_stats():
    from scale.scheduler import get_queue_stats
    return jsonify(get_queue_stats(g.org_id))

@app.route("/api/observability/traces", methods=["GET"])
@require_auth
def list_traces():
    from scale.observability import get_trace, get_slow_traces
    trace_id = request.args.get("trace_id")
    if trace_id:
        return jsonify(get_trace(trace_id))
    min_duration = request.args.get("min_duration_ms", 0, type=int)
    return jsonify(get_slow_traces(g.org_id, min_duration_ms=min_duration))

@app.route("/api/observability/metrics", methods=["POST"])
@require_auth
def record_obs_metric():
    from scale.observability import record_metric
    data = request.json
    return jsonify(record_metric(g.org_id, data["metric_name"], data["value"],
                                metric_type=data.get("type", "gauge"),
                                labels=data.get("labels"))), 201

@app.route("/api/observability/metrics", methods=["GET"])
@require_auth
def list_obs_metrics():
    from scale.observability import get_metrics, get_metric_summary
    metric_name = request.args.get("name")
    summary = request.args.get("summary", "false") == "true"
    if summary and metric_name:
        return jsonify(get_metric_summary(g.org_id, metric_name))
    return jsonify(get_metrics(g.org_id, metric_name=metric_name))

@app.route("/api/observability/logs", methods=["POST"])
@require_auth
def write_obs_log():
    from scale.observability import write_log
    data = request.json
    return jsonify(write_log(g.org_id, data["message"], level=data.get("level", "info"),
                            trace_id=data.get("trace_id"), source=data.get("source"),
                            metadata=data.get("metadata"))), 201

@app.route("/api/observability/logs", methods=["GET"])
@require_auth
def list_obs_logs():
    from scale.observability import get_logs, get_error_rate
    if request.args.get("error_rate") == "true":
        return jsonify(get_error_rate(g.org_id))
    level = request.args.get("level")
    trace_id = request.args.get("trace_id")
    return jsonify(get_logs(g.org_id, level=level, trace_id=trace_id))

@app.route("/api/observability/anomaly-rules", methods=["POST"])
@require_auth
def create_anomaly_rule():
    from scale.observability import create_anomaly_rule
    data = request.json
    rule = create_anomaly_rule(g.org_id, data["name"], data["metric_name"],
                               data["condition"], data["threshold"],
                               window_minutes=data.get("window_minutes", 5),
                               severity=data.get("severity", "warning"))
    return jsonify(rule), 201

@app.route("/api/observability/anomalies", methods=["GET"])
@require_auth
def list_anomalies():
    from scale.observability import check_anomalies, list_anomaly_events
    if request.args.get("check") == "true":
        return jsonify(check_anomalies(g.org_id))
    return jsonify(list_anomaly_events(g.org_id))

@app.route("/api/observability/anomalies/<event_id>/resolve", methods=["POST"])
@require_auth
def resolve_anomaly(event_id):
    from scale.observability import resolve_anomaly
    return jsonify(resolve_anomaly(event_id))

@app.route("/api/security/threat-rules", methods=["POST"])
@require_auth
def create_threat_rule():
    from scale.security import create_threat_rule
    data = request.json
    rule = create_threat_rule(g.org_id, data["name"], data["rule_type"],
                              config=data.get("config"), severity=data.get("severity", "warning"),
                              description=data.get("description"))
    return jsonify(rule), 201

@app.route("/api/security/threats", methods=["GET"])
@require_auth
def list_threats():
    from scale.security import get_threat_events, get_threat_summary
    if request.args.get("summary") == "true":
        return jsonify(get_threat_summary(g.org_id))
    return jsonify(get_threat_events(g.org_id))

@app.route("/api/security/threats", methods=["POST"])
@require_auth
def record_threat():
    from scale.security import record_threat_event
    data = request.json
    return jsonify(record_threat_event(g.org_id, data["event_type"],
                                       source_ip=data.get("source_ip"),
                                       details=data.get("details"),
                                       severity=data.get("severity", "warning"))), 201

@app.route("/api/regions", methods=["GET"])
def list_regions():
    from scale.security import list_regions
    return jsonify(list_regions())

@app.route("/api/regions", methods=["POST"])
@require_auth
@require_role("admin")
def create_region():
    from scale.security import create_region
    data = request.json
    return jsonify(create_region(data["region_name"], data["endpoint"],
                                weight=data.get("weight", 100),
                                features=data.get("features"))), 201

@app.route("/api/regions/<region_name>", methods=["PUT"])
@require_auth
@require_role("admin")
def update_region(region_name):
    from scale.security import update_region
    return jsonify(update_region(region_name, **request.json))

@app.route("/api/regions/<region_name>/assign", methods=["POST"])
@require_auth
@require_role("admin")
def assign_region(region_name):
    from scale.security import assign_org_region
    data = request.json or {}
    return jsonify(assign_org_region(g.org_id, region_name,
                                    priority=data.get("priority", 1))), 201

@app.route("/api/regions/my", methods=["GET"])
@require_auth
def my_regions():
    from scale.security import get_org_regions, get_best_region
    regions = get_org_regions(g.org_id)
    best = get_best_region(g.org_id)
    return jsonify({"regions": regions, "best": best})

@app.route("/api/developer/openapi.json", methods=["GET"])
def openapi_spec():
    return jsonify({
        "openapi": "3.0.3",
        "info": {"title": "AgentOS API", "version": "1.0.0",
                 "description": "AgentOS Developer API — build, integrate, and extend intelligent agents."},
        "servers": [{"url": "http://localhost:8000"}],
        "paths": {
            "/api/auth/register": {"post": {"summary": "Register user", "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "properties": {"email": {"type": "string"}, "password": {"type": "string"}, "name": {"type": "string"}}}}}}, "responses": {"201": {"description": "User created"}}}},
            "/api/auth/login": {"post": {"summary": "Login", "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "properties": {"email": {"type": "string"}, "password": {"type": "string"}}}}}}, "responses": {"200": {"description": "JWT token"}}}},
            "/api/auth/me": {"get": {"summary": "Get current user", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "User info"}}}},
            "/api/chat": {"post": {"summary": "Send message to agent", "security": [{"bearerAuth": []}], "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "properties": {"message": {"type": "string"}, "session_id": {"type": "string"}}}}}}, "responses": {"200": {"description": "Agent response"}}}},
            "/api/sessions": {"post": {"summary": "Create session", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Session created"}}}},
            "/api/sessions/{session_id}/messages": {"get": {"summary": "Get messages", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Messages"}}}},
            "/api/sessions/{session_id}/comments": {"get": {"summary": "List comments", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Comment list"}}}, "post": {"summary": "Add comment", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Comment created"}}}},
            "/api/sessions/{session_id}/feedback": {"get": {"summary": "Get feedback", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Feedback"}}}, "post": {"summary": "Submit feedback", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Feedback created"}}}},
            "/api/memory": {"get": {"summary": "List memories", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Memory list"}}}, "post": {"summary": "Save memory", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Memory saved"}}}},
            "/api/documents": {"get": {"summary": "List documents", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Document list"}}}},
            "/api/documents/upload": {"post": {"summary": "Upload document", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Document processed"}}}},
            "/api/plan": {"post": {"summary": "Generate plan", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Plan generated"}}}},
            "/api/usage": {"get": {"summary": "Usage analytics", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Usage data"}}}},
            "/api/orgs": {"post": {"summary": "Create organization", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Org created"}}}},
            "/api/orgs/{org_id}/members": {"get": {"summary": "List members", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Member list"}}}, "post": {"summary": "Add member", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Member added"}}}},
            "/api/orgs/{org_id}/invitations": {"get": {"summary": "List invitations", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Invitation list"}}}, "post": {"summary": "Create invitation", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Invitation created"}}}},
            "/api/orgs/{org_id}/audit": {"get": {"summary": "Get audit log", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Audit log"}}}},
            "/api/orgs/{org_id}/settings": {"get": {"summary": "Get org settings", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Settings"}}}, "put": {"summary": "Update org settings", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Settings updated"}}}},
            "/api/orgs/{org_id}/audit/export": {"get": {"summary": "Export audit log", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Export URL"}}}},
            "/api/orgs/{org_id}/compliance/snapshot": {"get": {"summary": "Get compliance snapshot", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Snapshot"}}}, "post": {"summary": "Generate compliance snapshot", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Snapshot created"}}}},
            "/api/orgs/{org_id}/admin/dashboard": {"get": {"summary": "Admin dashboard", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Dashboard data"}}}},
            "/api/orgs/{org_id}/rate-limits": {"get": {"summary": "Get rate limits", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Rate limits"}}}, "put": {"summary": "Update rate limits", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Rate limits updated"}}}},
            "/api/orgs/{org_id}/knowledge-bases": {"get": {"summary": "List knowledge bases", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Knowledge base list"}}}, "post": {"summary": "Create knowledge base", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Knowledge base created"}}}},
            "/api/knowledge-bases/{kb_id}/documents": {"get": {"summary": "List documents in KB", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Document list"}}}, "post": {"summary": "Add document to KB", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Document added"}}}},
            "/api/invitations/accept/{token}": {"post": {"summary": "Accept invitation", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Invitation accepted"}}}},
            "/api/invitations/pending": {"get": {"summary": "List pending invitations", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Pending invitations"}}}},
            "/api/templates": {"post": {"summary": "Create template", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Template created"}}}},
            "/api/templates/{template_id}": {"get": {"summary": "Get template", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Template"}}}},
            "/api/templates/{template_id}/fork": {"post": {"summary": "Fork template", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Template forked"}}}},
            "/api/orgs/{org_id}/templates": {"get": {"summary": "List org templates", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Template list"}}}},
            "/api/templates/public": {"get": {"summary": "List public templates", "responses": {"200": {"description": "Template list"}}}},
            "/api/developer/apps": {"get": {"summary": "List apps", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "App list"}}}, "post": {"summary": "Create app", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "App created"}}}},
            "/api/developer/apps/{app_id}": {"get": {"summary": "Get app", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "App details"}}}, "put": {"summary": "Update app", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "App updated"}}}, "delete": {"summary": "Delete app", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "App deleted"}}}},
            "/api/developer/keys": {"get": {"summary": "List API keys", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Key list"}}}, "post": {"summary": "Create API key", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Key created"}}}},
            "/api/developer/keys/{key_id}": {"delete": {"summary": "Revoke API key", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Key revoked"}}}},
            "/api/developer/usage": {"get": {"summary": "Usage analytics", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Usage data"}}}},
            "/api/developer/usage/org": {"get": {"summary": "Org usage analytics", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Org usage"}}}},
            "/api/developer/plugins": {"get": {"summary": "List plugins", "responses": {"200": {"description": "Plugin list"}}}, "post": {"summary": "Create plugin", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Plugin created"}}}},
            "/api/developer/plugins/{plugin_id}/publish": {"post": {"summary": "Publish plugin", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Plugin published"}}}},
            "/api/developer/plugins/{plugin_id}/install": {"post": {"summary": "Install plugin", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Plugin installed"}}}},
            "/api/developer/plugins/installed": {"get": {"summary": "List installed plugins", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Installed plugins"}}}},
            "/api/gdpr/export": {"post": {"summary": "Request GDPR data export", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Export started"}}}},
            "/api/gdpr/delete": {"post": {"summary": "Request GDPR data deletion", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Deletion started"}}}},
            "/api/gdpr/requests": {"get": {"summary": "List GDPR requests", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "GDPR requests"}}}},
            "/api/marketplace": {"get": {"summary": "Search marketplace", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Search results"}}}},
            "/api/marketplace/stats": {"get": {"summary": "Marketplace stats", "responses": {"200": {"description": "Stats"}}}},
            "/api/marketplace/packages": {"post": {"summary": "Create package", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Package created"}}}},
            "/api/marketplace/packages/{pkg_id}": {"get": {"summary": "Get package", "responses": {"200": {"description": "Package"}}}, "put": {"summary": "Update package", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Package updated"}}}},
            "/api/marketplace/packages/{pkg_id}/submit": {"post": {"summary": "Submit for review", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Submitted"}}}},
            "/api/marketplace/packages/{pkg_id}/approve": {"post": {"summary": "Approve package", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Approved"}}}},
            "/api/marketplace/packages/{pkg_id}/reject": {"post": {"summary": "Reject package", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Rejected"}}}},
            "/api/marketplace/packages/{pkg_id}/versions": {"get": {"summary": "List versions", "responses": {"200": {"description": "Version list"}}}, "post": {"summary": "Create version", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Version created"}}}},
            "/api/marketplace/packages/{pkg_id}/reviews": {"get": {"summary": "List reviews", "responses": {"200": {"description": "Review list"}}}, "post": {"summary": "Create review", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Review created"}}}},
            "/api/marketplace/packages/{pkg_id}/download": {"post": {"summary": "Download package", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Download recorded"}}}},
            "/api/marketplace/packages/{pkg_id}/pricing": {"get": {"summary": "Get pricing", "responses": {"200": {"description": "Pricing"}}}, "post": {"summary": "Set pricing", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Pricing set"}}}},
            "/api/marketplace/my-packages": {"get": {"summary": "My packages", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Package list"}}}},
            "/api/marketplace/revenue": {"get": {"summary": "Revenue analytics", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Revenue data"}}}},
            "/api/marketplace/payouts": {"get": {"summary": "List payouts", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Payout list"}}}, "post": {"summary": "Request payout", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Payout requested"}}}},
            "/api/kg/entities": {"get": {"summary": "List entities", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Entity list"}}}, "post": {"summary": "Create entity", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Entity created"}}}},
            "/api/kg/entities/{entity_id}": {"get": {"summary": "Get entity", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Entity"}}}, "put": {"summary": "Update entity", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Entity updated"}}}, "delete": {"summary": "Delete entity", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Entity deleted"}}}},
            "/api/kg/entities/{entity_id}/neighbors": {"get": {"summary": "Get entity neighbors", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Neighbors"}}}},
            "/api/kg/relationships": {"post": {"summary": "Create relationship", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Relationship created"}}}},
            "/api/kg/traverse": {"post": {"summary": "Traverse graph", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Traversal result"}}}},
            "/api/kg/path": {"post": {"summary": "Find path", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Path"}}}},
            "/api/kg/stats": {"get": {"summary": "Graph stats", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Stats"}}}},
            "/api/kg/snapshot": {"post": {"summary": "Graph snapshot", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Snapshot"}}}},
            "/api/scheduler/tasks": {"get": {"summary": "List tasks", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Task list"}}}, "post": {"summary": "Create task", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Task created"}}}},
            "/api/scheduler/tasks/{task_id}": {"get": {"summary": "Get task", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Task"}}}},
            "/api/scheduler/tasks/{task_id}/cancel": {"post": {"summary": "Cancel task", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Task cancelled"}}}},
            "/api/scheduler/stats": {"get": {"summary": "Scheduler stats", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Stats"}}}},
            "/api/observability/traces": {"get": {"summary": "List traces", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Trace list"}}}},
            "/api/observability/metrics": {"get": {"summary": "Get metrics", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Metrics"}}}, "post": {"summary": "Record metric", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Metric recorded"}}}},
            "/api/observability/logs": {"get": {"summary": "Query logs", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Logs"}}}, "post": {"summary": "Ingest log", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Log ingested"}}}},
            "/api/security/threat/rules": {"get": {"summary": "List threat rules", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Rule list"}}}, "post": {"summary": "Create threat rule", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Rule created"}}}},
            "/api/security/threat/events": {"get": {"summary": "List threat events", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Event list"}}}},
            "/api/brain/notes": {"get": {"summary": "List notes", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Note list"}}}, "post": {"summary": "Create note", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Note created"}}}},
            "/api/brain/notes/{note_id}": {"get": {"summary": "Get note", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Note"}}}, "put": {"summary": "Update note", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Note updated"}}}, "delete": {"summary": "Delete note", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Note deleted"}}}},
            "/api/brain/notes/{note_id}/backlinks": {"get": {"summary": "Get backlinks", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Backlinks"}}}},
            "/api/brain/search": {"get": {"summary": "Search notes", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Search results"}}}},
            "/api/brain/graph": {"get": {"summary": "Get graph data", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Graph data (nodes + edges)"}}}},
        },
        "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}}}
    })

@app.route("/api/developer/changelog", methods=["GET"])
def changelog():
    return jsonify([
        {"version": "1.1.0", "date": "2026-07-14", "changes": [
            "Obsidian Brain: personal knowledge graph with wiki-links, backlinks, graph viz",
            "Security: sandboxed code execution, command allowlist, rate limiting, refresh tokens",
            "Security: SQL injection fixes, session ownership checks, global JSON error handler",
            "Database: thread-safe connection pool with proper error handling",
            "Windows: SIGALRM fallback for plugin sandbox timeout",
        ]},
        {"version": "1.0.0", "date": "2026-07-13", "changes": [
            "Phase 5: Developer Ecosystem — apps, API keys, usage analytics, plugins",
            "Python SDK and TypeScript SDK available",
            "OpenAPI spec at /api/developer/openapi.json",
        ]},
        {"version": "0.4.0", "date": "2026-07-13", "changes": [
            "Phase 4: Enterprise SaaS — GDPR, data retention, IP allowlist, compliance snapshots",
        ]},
        {"version": "0.3.0", "date": "2026-07-13", "changes": [
            "Phase 3: Team Collaboration — invitations, audit logs, shared KBs, templates, comments, feedback",
        ]},
        {"version": "0.2.0", "date": "2026-07-13", "changes": [
            "Phase 2: Model Router, JWT auth, multi-tenancy",
        ]},
        {"version": "0.1.0", "date": "2026-07-13", "changes": [
            "Phase 0-1: Agent loop, tools, memory, knowledge, planning engine",
        ]},
    ])

@app.route("/api/developer/status", methods=["GET"])
def status_page():
    import time
    start = time.time()
    conn = get_pg()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        db_ms = int((time.time() - start) * 1000)
    finally:
        put_pg(conn)
    r = redis_conn()
    try:
        cache_ok = True
    except Exception:
        cache_ok = False
    return jsonify({
        "status": "operational",
        "timestamp": time.time(),
        "services": {
            "api": {"status": "operational", "latency_ms": 1},
            "database": {"status": "operational", "latency_ms": db_ms},
            "cache": {"status": "operational" if cache_ok else "degraded", "latency_ms": 1},
        },
        "version": "1.0.0",
    })

# ============================================================
# STATIC
# ============================================================
@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/jarvis")
def jarvis():
    return send_from_directory("static", "jarvis.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory("static", path)


# ============================================================
# VOICE PIPELINE (Socket.IO events)
# ============================================================
_voice_pipeline = None

def _init_voice_pipeline():
    """Initialize voice pipeline on first use."""
    global _voice_pipeline
    if _voice_pipeline is None:
        try:
            from voice.pipeline import VoicePipeline
            _voice_pipeline = VoicePipeline(
                on_wakeword=lambda: socketio.emit("voice.wake", namespace="/"),
                on_stt=lambda text: socketio.emit("voice.stt", {"text": text}, namespace="/"),
                on_tts_start=lambda: socketio.emit("voice.tts_start", namespace="/"),
                on_tts_end=lambda: socketio.emit("voice.tts_end", namespace="/"),
            )
        except ImportError:
            pass
    return _voice_pipeline

@app.route("/api/voice/start", methods=["POST"])
@require_auth
def voice_start():
    """Start voice pipeline (background wake word detection)."""
    pipeline = _init_voice_pipeline()
    if pipeline:
        pipeline.start()
        return jsonify({"status": "started"})
    return jsonify({"error": "Voice pipeline not available. Install: pip install openwakeword faster-whisper piper-tts"}), 503

@app.route("/api/voice/stop", methods=["POST"])
@require_auth
def voice_stop():
    """Stop voice pipeline."""
    global _voice_pipeline
    if _voice_pipeline:
        _voice_pipeline.stop()
        _voice_pipeline = None
    return jsonify({"status": "stopped"})

@app.route("/api/voice/speak", methods=["POST"])
@require_auth
def voice_speak():
    """Speak text via TTS."""
    data = request.json
    text = data.get("text", "")
    pipeline = _init_voice_pipeline()
    if pipeline:
        import threading
        threading.Thread(target=pipeline.speak, args=(text,), daemon=True).start()
        return jsonify({"status": "speaking"})
    return jsonify({"error": "Voice pipeline not available"}), 503

@app.route("/api/voice/transcribe", methods=["POST"])
@require_auth
def voice_transcribe():
    """Transcribe uploaded audio file."""
    if "audio" not in request.files:
        return jsonify({"error": "No audio file provided"}), 400

    audio_file = request.files["audio"]
    audio_bytes = audio_file.read()

    pipeline = _init_voice_pipeline()
    if not pipeline:
        return jsonify({"error": "Voice pipeline not available"}), 503

    import numpy as np
    # Convert to numpy array (assuming 16-bit PCM)
    audio_data = np.frombuffer(audio_bytes, dtype=np.int16)
    text = pipeline.transcribe(audio_data)
    return jsonify({"text": text or ""})

if __name__ == "__main__":
    # Auto-run SQLite migrations
    try:
        from migrate import run_migrations
        from database import _get_conn
        run_migrations(_get_conn())
        print("SQLite migrations applied successfully")
    except Exception as e:
        print(f"Migration warning: {e}")

    # Register Phase 9 expanded tools
    try:
        from tools import expanded
        print(f"Registered {len([k for k in dir(expanded) if not k.startswith('_')])} expanded tools")
    except Exception as e:
        print(f"Expanded tools warning: {e}")

    port = int(os.environ.get("PORT", 8000))
    socketio.run(app, host="0.0.0.0", port=port, debug=True, allow_unsafe_werkzeug=True)
