import os
import time
import uuid
import bcrypt
import jwt
from functools import wraps
from flask import request, jsonify, g
from typing import Optional
from database import pg_execute, pg_query, pg_execute_returning, redis_conn

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-in-production-" + uuid.uuid4().hex[:16])
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.environ.get("JWT_EXPIRY_HOURS", "72"))
REFRESH_EXPIRY_DAYS = int(os.environ.get("REFRESH_EXPIRY_DAYS", "30"))

# ============================================================
# TOKEN GENERATION
# ============================================================
def create_token(user_id: str, org_id: str = None, role: str = "member") -> str:
    jti = uuid.uuid4().hex
    payload = {
        "sub": user_id,
        "org_id": org_id,
        "role": role,
        "jti": jti,
        "iat": int(time.time()),
        "exp": int(time.time()) + (JWT_EXPIRY_HOURS * 3600),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    token = uuid.uuid4().hex + uuid.uuid4().hex
    exp = int(time.time()) + (REFRESH_EXPIRY_DAYS * 86400)
    pg_execute(
        "INSERT INTO refresh_tokens (id, user_id, expires_at) VALUES (%s, %s, to_timestamp(%s))",
        (token, user_id, exp)
    )
    return token

def rotate_refresh_token(old_token: str, user_id: str) -> Optional[str]:
    rows = pg_query(
        "SELECT id FROM refresh_tokens WHERE id = %s AND user_id = %s AND expires_at > NOW() AND revoked = FALSE",
        (old_token, user_id)
    )
    if not rows:
        return None
    pg_execute("UPDATE refresh_tokens SET revoked = TRUE WHERE id = %s", (old_token,))
    return create_refresh_token(user_id)

def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

# ============================================================
# PASSWORD HASHING
# ============================================================
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())

# ============================================================
# AUTH DECORATOR
# ============================================================
def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401

        token = auth_header[7:]
        payload = decode_token(token)
        if not payload:
            return jsonify({"error": "Invalid or expired token"}), 401

        # Set user context
        g.user_id = payload["sub"]
        g.org_id = payload.get("org_id")
        g.role = payload.get("role", "member")
        return f(*args, **kwargs)
    return decorated

def require_role(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not hasattr(g, 'role') or (g.role not in allowed_roles and g.role != 'owner'):
                return jsonify({"error": f"Insufficient permissions. Required: {allowed_roles}"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

# ============================================================
# ORGANIZATION MANAGEMENT
# ============================================================

def create_org(name: str, owner_user_id: str) -> dict:
    """Create an organization and make the user the owner."""
    import uuid
    org_id = str(uuid.uuid4())
    pg_execute(
        "INSERT INTO organizations (id, name, owner_id) VALUES (%s, %s, %s)",
        (org_id, name, owner_user_id)
    )
    # Add owner as member with owner role
    pg_execute(
        "INSERT INTO org_members (id, org_id, user_id, role) VALUES (%s, %s, %s, 'owner')",
        (str(uuid.uuid4()), org_id, owner_user_id)
    )
    return {"id": org_id, "name": name, "owner_id": owner_user_id}

def add_org_member(org_id: str, user_id: str, role: str = "member") -> dict:
    return pg_execute_returning(
        "INSERT INTO org_members (id, org_id, user_id, role) VALUES (%s, %s, %s, %s) RETURNING *",
        (str(uuid.uuid4()), org_id, user_id, role)
    )

def get_user_orgs(user_id: str) -> list[dict]:
    return pg_query(
        """SELECT o.id, o.name, om.role, o.created_at
           FROM organizations o
           JOIN org_members om ON o.id = om.org_id
           WHERE om.user_id = %s""",
        (user_id,)
    )

def get_org_members(org_id: str) -> list[dict]:
    return pg_query(
        """SELECT u.id, u.email, u.name, om.role, om.joined_at
           FROM org_members om
           JOIN users u ON om.user_id = u.id
           WHERE om.org_id = %s""",
        (org_id,)
    )

def is_org_member(org_id: str, user_id: str) -> bool:
    rows = pg_query(
        "SELECT 1 FROM org_members WHERE org_id = %s AND user_id = %s",
        (org_id, user_id)
    )
    return len(rows) > 0
