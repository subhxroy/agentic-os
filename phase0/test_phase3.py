import os
import sys
import uuid

os.environ["GEMINI_API_KEY"] = os.environ.get("GEMINI_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://agentos:agentos_dev@localhost:5432/agentos")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")

from database import pg_query
from auth.jwt_auth import create_token, hash_password
from memory.store import create_user, create_session
from collaboration.team import (
    create_invitation, accept_invitation, get_org_invitations,
    log_audit, get_audit_log,
    create_knowledge_base, get_org_knowledge_bases, add_document_to_kb, get_kb_documents,
    create_template, get_template, fork_template, get_org_templates,
    add_comment, get_session_comments, add_feedback, get_session_feedback
)

def _uid():
    return uuid.uuid4().hex[:8]

def _setup_org():
    email = f"org_admin_{_uid()}@test.com"
    user = create_user(email, hash_password("pass"), "Org Admin")
    from auth.jwt_auth import create_org
    org = create_org(f"Test Org {_uid()}", user["id"])
    return user, org

def test_invitation_flow():
    admin, org = _setup_org()
    invite = create_invitation(org["id"], f"newmember_{_uid()}@test.com", admin["id"], "member")
    assert invite is not None
    assert invite["status"] == "pending"
    invitations = get_org_invitations(org["id"])
    assert len(invitations) >= 1
    print(f"OK: Invitation created and listed")

def test_invitation_accept():
    admin, org = _setup_org()
    member_email = f"accept_{_uid()}@test.com"
    invite = create_invitation(org["id"], member_email, admin["id"], "member")
    member = create_user(member_email, hash_password("pass"), "Member")
    result = accept_invitation(invite["token"], member["id"])
    assert result is not None
    assert result["org_id"] == org["id"]
    print(f"OK: Invitation accepted, user added to org")

def test_audit_log():
    admin, org = _setup_org()
    log_audit(org["id"], admin["id"], "user.login",
              resource_type="user", resource_id=admin["id"],
              details={"email": admin["email"]})
    log_audit(org["id"], admin["id"], "session.create",
              resource_type="session", resource_id="test-session-id")
    logs = get_audit_log(org["id"])
    assert len(logs) >= 2
    assert logs[0]["action"] == "session.create"
    print(f"OK: Audit log works ({len(logs)} entries)")

def test_shared_knowledge_base():
    admin, org = _setup_org()
    kb = create_knowledge_base(org["id"], f"Team KB {_uid()}", admin["id"], "Shared docs")
    assert kb is not None
    assert kb["org_id"] == org["id"]
    kbs = get_org_knowledge_bases(org["id"])
    assert len(kbs) >= 1
    print(f"OK: Knowledge base created and listed")

def test_agent_template():
    admin, org = _setup_org()
    tmpl = create_template(
        created_by=admin["id"],
        name=f"Code Reviewer {_uid()}",
        description="Reviews code for bugs",
        system_prompt="You are a code reviewer.",
        tools=["read_file", "shell_command"],
        visibility="org",
        org_id=org["id"],
    )
    assert tmpl is not None
    assert tmpl["name"].startswith("Code Reviewer")
    found = get_template(tmpl["id"])
    assert found is not None
    print(f"OK: Agent template created and retrieved")

def test_template_fork():
    admin, org = _setup_org()
    original = create_template(
        created_by=admin["id"],
        name=f"Original {_uid()}",
        description="Original template",
        system_prompt="Be helpful.",
        tools=["calculator"],
        visibility="org",
        org_id=org["id"],
    )
    member_email = f"forker_{_uid()}@test.com"
    member = create_user(member_email, hash_password("pass"), "Forker")
    forked = fork_template(original["id"], member["id"], f"Forked {_uid()}")
    assert forked is not None
    assert forked["id"] != original["id"]
    # Check fork count incremented
    updated = get_template(original["id"])
    assert updated["fork_count"] == 1
    print(f"OK: Template forked (fork_count={updated['fork_count']})")

def test_comments():
    admin, org = _setup_org()
    session = create_session(admin["id"], "Test session")
    comment = add_comment(session["id"], admin["id"], "Great response!")
    assert comment is not None
    assert comment["content"] == "Great response!"
    comments = get_session_comments(session["id"])
    assert len(comments) == 1
    assert comments[0]["user_email"] == admin["email"]
    print(f"OK: Comments work ({len(comments)} comment)")

def test_feedback():
    admin, org = _setup_org()
    session = create_session(admin["id"], "Feedback session")
    fb = add_feedback(session["id"], admin["id"], 5, comment="Excellent!")
    assert fb is not None
    assert fb["rating"] == 5
    feedback = get_session_feedback(session["id"])
    assert len(feedback) == 1
    print(f"OK: Feedback works (rating={feedback[0]['rating']})")

def test_phase3_tables_exist():
    tables = pg_query("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    names = [t["tablename"] for t in tables]
    required = ["invitations", "audit_log", "knowledge_bases", "agent_templates",
                "template_forks", "comments", "feedback"]
    for t in required:
        assert t in names, f"Missing table: {t}"
    print(f"OK: All {len(required)} Phase 3 tables exist")

if __name__ == "__main__":
    test_phase3_tables_exist()
    test_invitation_flow()
    test_invitation_accept()
    test_audit_log()
    test_shared_knowledge_base()
    test_agent_template()
    test_template_fork()
    test_comments()
    test_feedback()
    print("\nAll Phase 3 tests passed!")
