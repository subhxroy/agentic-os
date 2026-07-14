import os
import sys
import tempfile

os.environ["GEMINI_API_KEY"] = "test-fake-key"

import tools.registry
import tools.web_search
from memory import store
from agent.prompt_builder import build_system_prompt, parse_tool_call
from tools.registry import execute_tool

def test_tools_loaded():
    names = list(tools.registry.TOOL_REGISTRY.keys())
    assert "calculator" in names
    assert "file_search" in names
    assert "read_file" in names
    assert "web_search" in names
    print(f"OK: {len(names)} tools loaded: {names}")

def test_calculator():
    result = execute_tool("calculator", {"expression": "2 + 2"})
    assert "4" in result
    print(f"OK: calculator(2+2) = {result}")

def test_calculator_sqrt():
    result = execute_tool("calculator", {"expression": "sqrt(144)"})
    assert "12" in result
    print(f"OK: calculator(sqrt(144)) = {result}")

def test_parse_tool_call_json_block():
    text = 'Some text\n```json\n{"tool": "calculator", "args": {"expression": "2+2"}}\n```\nmore text'
    result = parse_tool_call(text)
    assert result is not None
    assert result["tool"] == "calculator"
    assert result["args"]["expression"] == "2+2"
    print(f"OK: parse_tool_call JSON block: {result}")

def test_parse_tool_call_no_match():
    text = "I don't need any tools for this simple question."
    result = parse_tool_call(text)
    assert result is None
    print("OK: parse_tool_call no match = None")

def test_memory_db():
    from memory.store import create_user, create_session, save_message, get_conversation_history, remember, recall
    import uuid
    email = f"memtest_{uuid.uuid4().hex[:8]}@example.com"
    user = create_user(email, "hash", "MemTest")
    session = create_session(user["id"])
    save_message(session["id"], "user", "Hello")
    save_message(session["id"], "assistant", "Hi there!")
    remember(user["id"], "user_name", "Alice", importance=0.9)
    history = get_conversation_history(session["id"])
    assert len(history) >= 2
    assert history[-1]["role"] == "assistant"
    recalled = recall(user["id"], "user_name")
    assert recalled == "Alice"
    print(f"OK: memory store works ({len(history)} msgs, recall={recalled})")

def test_system_prompt():
    prompt = build_system_prompt()
    assert "calculator" in prompt
    assert "file_search" in prompt
    assert "read_file" in prompt
    assert "web_search" in prompt
    assert "Tool" in prompt
    print(f"OK: system prompt ({len(prompt)} chars) includes all tools")

def test_file_search():
    result = execute_tool("file_search", {"pattern": "*.py", "path": "."})
    assert "cli.py" in result or "test_agent" in result
    print(f"OK: file_search found Python files: {result[:100]}")

if __name__ == "__main__":
    test_tools_loaded()
    test_calculator()
    test_calculator_sqrt()
    test_parse_tool_call_json_block()
    test_parse_tool_call_no_match()
    test_system_prompt()
    test_file_search()
    test_memory_db()
    print("\nAll tests passed!")
