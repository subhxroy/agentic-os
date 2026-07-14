import json
from tools.registry import get_tool_definitions

SYSTEM_PROMPT_TEMPLATE = """You are an AI agent running in an Agentic Operating System. You have access to tools that you can use to accomplish goals.

## Available Tools
{tool_descriptions}

## How to Use Tools
When you need to use a tool, respond with a JSON block exactly like this:
```json
{{
  "tool": "tool_name",
  "args": {{ "param1": "value1" }}
}}
```

After receiving the tool result, continue your reasoning.

## Your memories
{memories}

## Instructions
- Break down complex goals into steps
- Use tools when needed, reason when not
- Keep responses concise and actionable
- If you hit an error, explain it and try a different approach
- When the goal is complete, summarize what you did"""

def build_system_prompt() -> str:
    tools = get_tool_definitions()
    tool_lines = []
    for t in tools:
        params = t.get("input_schema", {}).get("properties", {})
        param_str = ", ".join(f"{p}: {info.get('description', '')}" for p, info in params.items())
        tool_lines.append(f"- {t['name']}: {t['description']}  Args: {param_str}")
    return SYSTEM_PROMPT_TEMPLATE.format(
        tool_descriptions="\n".join(tool_lines),
        memories="(no persistent memories yet)"
    )

def parse_tool_call(content: str) -> dict | None:
    import re
    match = re.search(r'```(?:json)?\s*\n?(\{.*?"tool".*?\})\s*\n?```', content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None

    match = re.search(r'\{[^{}]*"tool"[^{}]*"args"[^{}]*\}', content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None
