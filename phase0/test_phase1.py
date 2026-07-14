import os
import sys
import uuid

os.environ["GEMINI_API_KEY"] = "test-fake-key"
os.environ.setdefault("DATABASE_URL", "postgresql://agentos:agentos_dev@localhost:5432/agentos")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")

import tools.registry
import tools.web_search
from database import pg_query, pg_execute
from memory.store import (
    create_user, get_user_by_email, create_session,
    save_message, get_conversation_history,
    set_working_memory, get_working_memory, clear_working_memory
)
from knowledge.ingest import chunk_text, upload_document, process_document, search_knowledge
from agent.planner import PlanningEngine

def _uid():
    return uuid.uuid4().hex[:8]

def test_tools_loaded():
    names = list(tools.registry.TOOL_REGISTRY.keys())
    assert "calculator" in names
    assert "file_search" in names
    assert "read_file" in names
    assert "web_search" in names
    assert "get_datetime" in names
    assert "knowledge_search" in names
    assert "shell_command" in names
    assert "code_execute" in names
    assert "json_query" in names
    assert "write_file" in names
    print(f"OK: {len(names)} tools loaded: {names}")

def test_calculator():
    result = tools.registry.execute_tool("calculator", {"expression": "2 + 2"})
    assert "4" in result
    print(f"OK: calculator(2+2) = {result}")

def test_database_connection():
    rows = pg_query("SELECT 1 AS test")
    assert rows[0]["test"] == 1
    print("OK: PostgreSQL connection works")

def test_user_creation():
    email = f"test_{_uid()}@example.com"
    user = create_user(email, "hashed_password_123", "Test User")
    assert user is not None
    assert user["email"] == email
    found = get_user_by_email(email)
    assert found is not None
    print(f"OK: User created: {user['id']}")

def test_session_creation():
    email = f"session_{_uid()}@example.com"
    user = create_user(email, "hash", "Session Test")
    session = create_session(user["id"], "Test goal")
    assert session is not None
    assert session["goal"] == "Test goal"
    print(f"OK: Session created: {session['id']}")

def test_conversation_persistence():
    email = f"conv_{_uid()}@example.com"
    user = create_user(email, "hash", "Conv Test")
    session = create_session(user["id"])
    save_message(session["id"], "user", "Hello")
    save_message(session["id"], "assistant", "Hi there!")
    history = get_conversation_history(session["id"])
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"
    print(f"OK: Conversations persist ({len(history)} messages)")

def test_redis_working_memory():
    email = f"redis_{_uid()}@example.com"
    user = create_user(email, "hash", "Redis Test")
    session = create_session(user["id"])
    set_working_memory(session["id"], "step", "analysis")
    set_working_memory(session["id"], "data", {"count": 42})
    step = get_working_memory(session["id"], "step")
    data = get_working_memory(session["id"], "data")
    assert step == "analysis"
    assert data == {"count": 42}
    clear_working_memory(session["id"])
    assert get_working_memory(session["id"], "step") is None
    print("OK: Redis working memory works")

def test_chunking():
    text = "This is a test document. " * 100
    chunks = chunk_text(text, chunk_size=20, overlap=5)
    assert len(chunks) > 1
    print(f"OK: Text chunked into {len(chunks)} pieces")

def test_document_upload():
    email = f"doc_{_uid()}@example.com"
    user = create_user(email, "hash", "Doc Test")
    content = b"Test document content for knowledge system"
    doc = upload_document(user["id"], "test.txt", content)
    assert doc is not None
    assert doc["status"] == "pending"
    print(f"OK: Document uploaded: {doc['id']}")

def test_tool_parse():
    from agent.prompt_builder import parse_tool_call
    text = '```json\n{"tool": "calculator", "args": {"expression": "2+2"}}\n```'
    result = parse_tool_call(text)
    assert result is not None
    assert result["tool"] == "calculator"
    print("OK: Tool call parsing works")

def test_prompt_builder():
    from agent.prompt_builder import build_system_prompt
    prompt = build_system_prompt()
    assert "calculator" in prompt
    assert "file_search" in prompt
    assert "read_file" in prompt
    assert "web_search" in prompt
    assert "get_datetime" in prompt
    assert "knowledge_search" in prompt
    assert "shell_command" in prompt
    assert "code_execute" in prompt
    assert "json_query" in prompt
    assert "write_file" in prompt
    print(f"OK: System prompt built ({len(prompt)} chars)")

if __name__ == "__main__":
    test_tools_loaded()
    test_calculator()
    test_database_connection()
    test_user_creation()
    test_session_creation()
    test_conversation_persistence()
    test_redis_working_memory()
    test_chunking()
    test_document_upload()
    test_tool_parse()
    test_prompt_builder()
    print("\nAll Phase 1 tests passed!")
