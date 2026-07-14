import json
import re
import math
import os
from datetime import datetime, timedelta, timezone

TOOL_REGISTRY: dict[str, dict] = {}
_PENDING_CONFIRMATIONS: dict[str, dict] = {}

def tool(name: str, description: str, parameters: dict, destructive: bool = False):
    def decorator(fn):
        TOOL_REGISTRY[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "fn": fn,
            "destructive": destructive,
        }
        return fn
    return decorator

def get_tool_definitions() -> list[dict]:
    return [
        {
            "name": info["name"],
            "description": info["description"],
            "input_schema": info["parameters"],
        }
        for info in TOOL_REGISTRY.values()
    ]

def execute_tool(name: str, args: dict, confirmed: bool = False) -> str:
    info = TOOL_REGISTRY.get(name)
    if not info:
        return json.dumps({"error": f"Unknown tool: {name}"})
    if info.get("destructive") and not confirmed:
        reason = f"Tool '{name}' requires destructive action permission"
        return json.dumps({"requires_confirmation": True, "tool": name, "reason": reason, "args": args})
    try:
        result = info["fn"](**args)
        return json.dumps({"result": result}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

def confirm_tool(name: str, args: dict) -> str:
    return execute_tool(name, args, confirmed=True)

_SAFE_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bool": bool, "chr": chr,
    "dict": dict, "divmod": divmod, "enumerate": enumerate, "filter": filter,
    "float": float, "format": format, "frozenset": frozenset, "hex": hex,
    "int": int, "isinstance": isinstance, "iter": iter, "len": len,
    "list": list, "map": map, "max": max, "min": min, "next": next,
    "object": object, "oct": oct, "ord": ord, "pow": pow, "range": range,
    "reversed": reversed, "round": round, "set": set, "slice": slice,
    "sorted": sorted, "str": str, "sum": sum, "tuple": tuple, "type": type,
    "zip": zip, "True": True, "False": False, "None": None,
    "math": math, "json": json, "re": re,
    "datetime": datetime, "timedelta": timedelta,
}

_ALLOWED_COMMANDS = {
    "ls", "dir", "pwd", "whoami", "date", "echo", "cat", "head", "tail",
    "git", "npm", "node", "python", "pip", "docker", "uname", "hostname",
    "uptime", "free", "df", "ps", "netstat",
}

@tool(
    name="calculator",
    description="Evaluate a mathematical expression. Use for any arithmetic or math calculation.",
    parameters={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "The mathematical expression to evaluate (e.g., '2 + 2', 'sqrt(144)', '3 * 7 + 2')",
            }
        },
        "required": ["expression"],
    },
)
def calculator(expression: str) -> str:
    safe = re.sub(r'[^0-9+\-*/().,% sqrtpi^]', '', expression)
    safe = safe.replace('^', '**')
    result = eval(safe, {"__builtins__": {}}, {"sqrt": math.sqrt, "pi": math.pi})
    return f"{expression} = {result}"

@tool(
    name="file_search",
    description="Search for files matching a pattern. Use to find files in the project.",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern to search for (e.g., '*.py', '**/*.md')",
            },
            "path": {
                "type": "string",
                "description": "Directory to search in (default: current directory)",
            },
        },
        "required": ["pattern"],
    },
)
def file_search(pattern: str, path: str = ".") -> list[str]:
    import glob
    import os
    full_pattern = os.path.join(path, "**", pattern)
    matches = glob.glob(full_pattern, recursive=True)
    return matches[:50]

@tool(
    name="read_file",
    description="Read the contents of a file. Use to inspect files in the project.",
    parameters={
        "type": "object",
        "properties": {
            "filepath": {
                "type": "string",
                "description": "Path to the file to read",
            },
            "max_lines": {
                "type": "integer",
                "description": "Maximum number of lines to read",
            },
        },
        "required": ["filepath"],
    },
)
def read_file(filepath: str, max_lines: int = 100) -> str:
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    content = ''.join(lines[:max_lines])
    if len(lines) > max_lines:
        content += f"\n... (truncated, {len(lines)} total lines)"
    return content

@tool(
    name="get_datetime",
    description="Get the current date and time. Use when you need to know what time it is.",
    parameters={
        "type": "object",
        "properties": {},
    },
)
def get_datetime() -> str:
    from datetime import datetime
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")

@tool(
    name="knowledge_search",
    description="Search the knowledge base for relevant documents. Use to find information from uploaded documents.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to find relevant knowledge",
            },
            "user_id": {
                "type": "string",
                "description": "The user ID to search knowledge for",
            },
        },
        "required": ["query", "user_id"],
    },
)
def knowledge_search(query: str, user_id: str) -> str:
    from knowledge.ingest import search_knowledge
    results = search_knowledge(user_id, query, limit=5)
    if not results:
        return "No relevant knowledge found."
    formatted = []
    for i, r in enumerate(results, 1):
        formatted.append(f"[{i}] (score: {r['score']:.2f}) {r['content'][:200]}")
    return "\n".join(formatted)

_ALLOWED_COMMANDS = {
    "ls", "dir", "pwd", "whoami", "date", "echo", "cat", "head", "tail",
    "git", "npm", "node", "python", "pip", "docker", "uname", "hostname",
    "uptime", "free", "df", "ps", "netstat",
}

@tool(
    name="shell_command",
    description="Execute a shell command and return its output. Use for system operations, git, npm, etc.",
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 30)",
            },
        },
        "required": ["command"],
    },
)
def shell_command(command: str, timeout: int = 30) -> str:
    base = command.strip().split()[0].lower() if command.strip() else ""
    if base not in _ALLOWED_COMMANDS:
        return f"Error: Command '{base}' not allowed. Allowed: {', '.join(sorted(_ALLOWED_COMMANDS))}"
    import subprocess
    result = subprocess.run(
        command, shell=True, capture_output=True, text=True, timeout=timeout
    )
    output = result.stdout
    if result.stderr:
        output += f"\nSTDERR: {result.stderr}"
    if result.returncode != 0:
        output += f"\nExit code: {result.returncode}"
    return output[:5000] if output else "Command produced no output"

_SAFE_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bool": bool, "chr": chr,
    "dict": dict, "divmod": divmod, "enumerate": enumerate, "filter": filter,
    "float": float, "format": format, "frozenset": frozenset, "hex": hex,
    "int": int, "isinstance": isinstance, "iter": iter, "len": len,
    "list": list, "map": map, "max": max, "min": min, "next": next,
    "object": object, "oct": oct, "ord": ord, "pow": pow, "range": range,
    "reversed": reversed, "round": round, "set": set, "slice": slice,
    "sorted": sorted, "str": str, "sum": sum, "tuple": tuple, "type": type,
    "zip": zip, "True": True, "False": False, "None": None,
    "math": math, "json": json, "re": re,
    "datetime": datetime, "timedelta": timedelta,
}

_ALLOWED_COMMANDS = {
    "ls", "dir", "pwd", "whoami", "date", "echo", "cat", "head", "tail",
    "git", "npm", "node", "python", "pip", "docker", "uname", "hostname",
    "uptime", "free", "df", "ps", "netstat",
}

@tool(
    name="code_execute",
    description="Execute Python code and return the result. Use for data processing, calculations, or testing logic.",
    parameters={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code to execute",
            },
        },
        "required": ["code"],
    },
)
def code_execute(code: str) -> str:
    import io
    import contextlib
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            exec(code, {"__builtins__": _SAFE_BUILTINS}, {})
        output = buffer.getvalue()
        return output[:5000] if output else "Code executed successfully (no output)"
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"

@tool(
    name="json_query",
    description="Query a JSON string using a simple dot-notation path. Use to extract data from JSON.",
    parameters={
        "type": "object",
        "properties": {
            "json_str": {
                "type": "string",
                "description": "The JSON string to query",
            },
            "path": {
                "type": "string",
                "description": "Dot-notation path (e.g., 'data.users.0.name')",
            },
        },
        "required": ["json_str", "path"],
    },
)
def json_query(json_str: str, path: str) -> str:
    data = json.loads(json_str)
    parts = path.split(".")
    current = data
    for part in parts:
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            return f"Cannot navigate into {type(current).__name__} at '{part}'"
    return json.dumps(current, indent=2, ensure_ascii=False) if not isinstance(current, str) else current

@tool(
    name="write_file",
    description="Write content to a file. Use to create or update files in the project.",
    parameters={
        "type": "object",
        "properties": {
            "filepath": {
                "type": "string",
                "description": "Path to the file to write",
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file",
            },
        },
        "required": ["filepath", "content"],
    },
)
def write_file(filepath: str, content: str) -> str:
    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    return f"Written {len(content)} bytes to {filepath}"

# ============================================================
# Phase 8: PERMISSION-GATED TOOLS
# ============================================================
# Tools flagged destructive=True require user confirmation
# before execution (UI shows "awaiting_confirmation" state).

def require_confirmation(name: str, reason: str) -> dict:
    """Return a confirmation-required signal to the agent loop."""
    return json.dumps({"requires_confirmation": True, "tool": name, "reason": reason})

_SANDBOX_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sandbox"))
os.makedirs(_SANDBOX_DIR, exist_ok=True)

@tool(
    name="sandbox_read",
    description="Read a file from the isolated sandbox directory. Safe for any content.",
    parameters={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Filename within the sandbox directory",
            },
        },
        "required": ["filename"],
    },
)
def sandbox_read(filename: str) -> str:
    path = os.path.normpath(os.path.join(_SANDBOX_DIR, filename))
    if not path.startswith(_SANDBOX_DIR):
        return "Error: Path traversal detected."
    if not os.path.exists(path):
        return f"Error: File '{filename}' not found in sandbox."
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()[:10000]

@tool(
    name="sandbox_write",
    description="Write a file inside the isolated sandbox directory.",
    parameters={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Filename within the sandbox directory",
            },
            "content": {
                "type": "string",
                "description": "Content to write",
            },
        },
        "required": ["filename", "content"],
    },
)
def sandbox_write(filename: str, content: str) -> str:
    path = os.path.normpath(os.path.join(_SANDBOX_DIR, filename))
    if not path.startswith(_SANDBOX_DIR):
        return "Error: Path traversal detected."
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Written {len(content)} bytes to sandbox/{filename}"

@tool(
    name="sandbox_exec",
    description="Execute arbitrary Python code inside the sandbox. PERMISSION REQUIRED.",
    parameters={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code to execute in the sandbox",
            },
        },
        "required": ["code"],
    },
    destructive=True,
)
def sandbox_exec(code: str) -> str:
    import io, contextlib
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            exec(code, {"__builtins__": _SAFE_BUILTINS}, {})
        output = buffer.getvalue()
        return output[:5000] if output else "Code executed successfully (no output)"
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"

@tool(
    name="browser_navigate",
    description="Navigate to a URL via headless browser and return page text. PERMISSION REQUIRED.",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to navigate to",
            },
        },
        "required": ["url"],
    },
    destructive=True,
)
def browser_navigate(url: str) -> str:
    import subprocess, sys, tempfile
    script = f"""
import asyncio
async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("{url}", timeout=30000)
        text = await page.inner_text("body")
        await browser.close()
        return text[:8000]
import sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
result = asyncio.run(main())
print(result)
"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            return f"Browser error: {result.stderr[:1000]}"
        return result.stdout[:8000] or "Page loaded but produced no text."
    except subprocess.TimeoutExpired:
        return "Error: Browser navigation timed out after 60s."
    except FileNotFoundError:
        return "Error: Playwright not installed. Run: pip install playwright && playwright install chromium"

@tool(
    name="email_send",
    description="Send an email via SMTP. PERMISSION REQUIRED.",
    parameters={
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient email address"},
            "subject": {"type": "string", "description": "Email subject"},
            "body": {"type": "string", "description": "Email body text"},
        },
        "required": ["to", "subject", "body"],
    },
    destructive=True,
)
def email_send(to: str, subject: str, body: str) -> str:
    import smtplib, os
    smtp_host = os.environ.get("SMTP_HOST", "smtp.ethereal.email")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    if not smtp_user:
        smtp_host = "sandbox"
    if smtp_host == "sandbox":
        return f"[Sandbox] Email queued: to={to}, subject={subject}, body={body[:200]}"
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            msg = f"Subject: {subject}\n\n{body}"
            server.sendmail(smtp_user, [to], msg)
        return f"Email sent to {to} successfully."
    except Exception as e:
        return f"Email error: {e}"

@tool(
    name="calendar_event",
    description="Schedule a calendar event. PERMISSION REQUIRED.",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Event title"},
            "start_time": {"type": "string", "description": "Start time (ISO 8601, e.g. 2026-07-14T14:00:00Z)"},
            "end_time": {"type": "string", "description": "End time (ISO 8601)"},
            "description": {"type": "string", "description": "Event description"},
        },
        "required": ["title", "start_time", "end_time"],
    },
    destructive=True,
)
def calendar_event(title: str, start_time: str, end_time: str, description: str = "") -> str:
    return f"[Sandbox] Calendar event created: '{title}' from {start_time} to {end_time}. Description: {description}"

@tool(
    name="schedule_task",
    description="Create a scheduled task. Use for recurring or delayed operations.",
    parameters={
        "type": "object",
        "properties": {
            "task_type": {"type": "string", "description": "Type of task (e.g. 'email_report', 'data_purge')"},
            "payload": {"type": "object", "description": "Task payload data"},
            "priority": {"type": "integer", "description": "Priority (1-10, higher=more important)"},
        },
        "required": ["task_type", "payload"],
    },
)
def schedule_task(task_type: str, payload: dict = {}, priority: int = 5) -> str:
    try:
        from scale.scheduler import create_task
        import uuid
        task = create_task("system", task_type, payload=payload, priority=priority)
        return f"Task created: {task.get('id', 'unknown')} (type={task_type}, priority={priority})"
    except ImportError:
        return f"[Sandbox] Task queued: type={task_type}, priority={priority}, payload={json.dumps(payload)[:200]}"
    except Exception as e:
        return f"Scheduler error: {e}"

@tool(
    name="memory_recall",
    description="Retrieve long-term memories matching a query.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query to find relevant memories"},
            "limit": {"type": "integer", "description": "Maximum number of memories to return"},
        },
        "required": ["query"],
    },
)
def memory_recall(query: str, limit: int = 5) -> str:
    try:
        from memory.store import recall
        results = recall(query, limit=limit)
        if not results:
            return "No relevant memories found."
        formatted = []
        for r in results:
            formatted.append(f"[{r.get('importance', 0):.1f}] {r.get('content', '')[:300]}")
        return "\n".join(formatted)
    except ImportError:
        return f"[Sandbox] Memory recall for query='{query}': no backend available."
    except Exception as e:
        return f"Memory recall error: {e}"

@tool(
    name="memory_store",
    description="Store a long-term memory for future recall.",
    parameters={
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "Memory key for retrieval"},
            "content": {"type": "string", "description": "Memory content to store"},
            "importance": {"type": "number", "description": "Importance score (0.0 to 1.0)"},
        },
        "required": ["key", "content"],
    },
)
def memory_store(key: str, content: str, importance: float = 0.5) -> str:
    try:
        from memory.store import remember
        remember("system", key, content, importance=importance)
        return f"Memory stored: key='{key}', importance={importance}"
    except ImportError:
        return f"[Sandbox] Memory stored: key='{key}', content='{content[:100]}'"
    except Exception as e:
        return f"Memory store error: {e}"
