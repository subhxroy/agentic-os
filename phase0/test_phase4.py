import os
import sys
import uuid
import json

os.environ["GEMINI_API_KEY"] = os.environ.get("GEMINI_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://agentos:agentos_dev@localhost:5432/agentos")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")

from database import pg_query
from auth.jwt_auth import create_token, hash_password, create_org
from memory.store import create_user, create_session
from collaboration.team import log_audit

def _uid():
    return uuid.uuid4().hex[:8]

def _setup_org():
    email = f"ent_admin_{_uid()}@test.com"
    user = create_user(email, hash_password("pass"), "Enterprise Admin")
    org = create_org(f"Enterprise Org {_uid()}", user["id"])
    return user, org

def test_phase4_tables_exist():
    tables = pg_query("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    names = [t["tablename"] for t in tables]
    required = ["org_settings", "gdpr_requests", "session_policies",
                "compliance_snapshots", "rate_limit_configs", "export_log"]
    for t in required:
        assert t in names, f"Missing table: {t}"
    print(f"OK: All {len(required)} Phase 4 tables exist")

def test_org_settings():
    from enterprise.compliance import upsert_org_settings, get_org_settings
    _, org = _setup_org()
    settings = upsert_org_settings(org["id"], {
        "ip_allowlist": ["10.0.0.0/8", "192.168.1.0/24"],
        "mfa_required": True,
        "session_duration_hours": 8,
        "conversation_retention_days": 30,
        "data_classification": "confidential",
        "soc2_enabled": True,
    })
    assert settings is not None
    assert settings["mfa_required"] == True
    assert settings["data_classification"] == "confidential"
    # Update
    upsert_org_settings(org["id"], {"mfa_required": False})
    updated = get_org_settings(org["id"])
    assert updated["mfa_required"] == False
    print(f"OK: Org settings create/update works")

def test_ip_allowlist():
    from enterprise.compliance import upsert_org_settings, check_ip_allowed
    _, org = _setup_org()
    upsert_org_settings(org["id"], {"ip_allowlist": ["10.0.0.0/8", "192.168.1.0/24"]})
    assert check_ip_allowed(org["id"], "10.1.2.3") == True
    assert check_ip_allowed(org["id"], "192.168.1.100") == True
    assert check_ip_allowed(org["id"], "203.0.113.1") == False
    # No restriction = allow all
    _, org2 = _setup_org()
    assert check_ip_allowed(org2["id"], "any.ip.here") == True
    print(f"OK: IP allowlist works")

def test_gdpr_export():
    from enterprise.compliance import request_data_export, process_data_export
    user, org = _setup_org()
    session = create_session(user["id"], "GDPR test session")
    req = request_data_export(user["id"])
    assert req["status"] == "pending"
    result = process_data_export(req["id"])
    assert result["status"] == "completed"
    assert result["record_count"] >= 0
    # Verify file exists
    assert os.path.exists(result["file"])
    print(f"OK: GDPR export works (file: {result['file']})")

def test_gdpr_deletion():
    from enterprise.compliance import request_data_deletion, process_data_deletion
    user, org = _setup_org()
    session = create_session(user["id"], "Deletion test")
    req = request_data_deletion(user["id"])
    result = process_data_deletion(req["id"])
    assert result["status"] == "completed"
    # Verify user anonymized
    from memory.store import get_user_by_id
    deleted_user = get_user_by_id(user["id"])
    assert "anonymized" in deleted_user["email"]
    print(f"OK: GDPR deletion works (user anonymized)")

def test_compliance_snapshot():
    from enterprise.compliance import generate_compliance_snapshot
    user, org = _setup_org()
    log_audit(org["id"], user["id"], "user.login")
    snapshot = generate_compliance_snapshot(org["id"])
    assert snapshot is not None
    assert snapshot["total_users"] >= 1
    assert snapshot["audit_log_count"] >= 1
    print(f"OK: Compliance snapshot works (users={snapshot['total_users']})")

def test_audit_export():
    from enterprise.compliance import export_audit_log
    user, org = _setup_org()
    log_audit(org["id"], user["id"], "test.action", details={"key": "value"})
    result = export_audit_log(org["id"], format="json", days=7, user_id=user["id"])
    assert result["record_count"] >= 1
    assert os.path.exists(result["file"])
    print(f"OK: Audit export works ({result['record_count']} records)")

def test_admin_dashboard():
    from enterprise.compliance import get_admin_dashboard
    user, org = _setup_org()
    dashboard = get_admin_dashboard(org["id"])
    assert "members" in dashboard
    assert "settings" in dashboard
    assert "usage_7d" in dashboard
    assert "compliance_snapshot" in dashboard
    assert "gdpr_pending" in dashboard
    assert len(dashboard["members"]) >= 1
    print(f"OK: Admin dashboard works ({len(dashboard['members'])} members)")

def test_rate_limit_config():
    from database import pg_query, pg_execute, pg_execute_returning
    _, org = _setup_org()
    pg_execute(
        "INSERT INTO rate_limit_configs (id, org_id, requests_per_minute, requests_per_hour) VALUES (%s, %s, 120, 5000)",
        (str(uuid.uuid4()), org["id"])
    )
    rows = pg_query("SELECT * FROM rate_limit_configs WHERE org_id = %s", (org["id"],))
    assert len(rows) == 1
    assert rows[0]["requests_per_minute"] == 120
    print(f"OK: Rate limit config works")

if __name__ == "__main__":
    test_phase4_tables_exist()
    test_org_settings()
    test_ip_allowlist()
    test_gdpr_export()
    test_gdpr_deletion()
    test_compliance_snapshot()
    test_audit_export()
    test_admin_dashboard()
    test_rate_limit_config()
    print("\nAll Phase 4 tests passed!")
