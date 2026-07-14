import json
import os
import re
from tools.registry import execute_tool, confirm_tool
from memory.store import save_message, get_conversation_history, set_working_memory, get_working_memory
from agent.prompt_builder import build_system_prompt, parse_tool_call
from agent.model_router import ModelRouter
import tools.web_search
from flask_socketio import SocketIO

MAX_ITERATIONS = 25

class AgentLoop:
    def __init__(self):
        self.router = ModelRouter()
        self.socketio = None

    def set_socketio(self, sio: SocketIO):
        self.socketio = sio

    def _emit(self, event: str, data: dict):
        if self.socketio:
            try:
                self.socketio.emit(event, data, namespace="/")
            except Exception:
                pass

    def run(self, session_id: str, user_id: str, user_input: str,
            tier: str = "cost_optimized") -> str:
        # Load conversation history from PostgreSQL
        history = get_conversation_history(session_id, limit=20)
        contents = []
        for msg in history:
            role = "user" if msg["role"] == "user" else "model"
            text = msg["content"]
            if msg.get("tool_calls"):
                text += f"\n\n[Tool calls: {json.dumps(msg['tool_calls'])}]"
            if msg.get("tool_results"):
                text += f"\n\n[Tool results: {msg['tool_results']}]"
            contents.append({"role": role, "text": text})

        contents.append({"role": "user", "text": user_input})
        save_message(session_id, "user", user_input)

        # Store current state in working memory (Redis)
        set_working_memory(session_id, "current_input", user_input)

        sys_instruction = build_system_prompt()

        for iteration in range(MAX_ITERATIONS):
            result = self.router.generate_content(
                system_instruction=sys_instruction,
                contents=contents,
                tier=tier,
            )

            if result.get("error"):
                return f"Error: {result['error']}"

            content = result["text"]
            if not content:
                return "No response from model."

            contents.append({"role": "model", "text": content})

            tool_call = parse_tool_call(content)
            if tool_call:
                tool_name = tool_call.get("tool")
                args = tool_call.get("args", {})
                save_message(session_id, "assistant", content, tool_calls=[tool_call])

                self._emit("tool_call", {
                    "session_id": session_id,
                    "tool_name": tool_name,
                    "args": args,
                })

                result = execute_tool(tool_name, args)

                try:
                    parsed = json.loads(result)
                except (json.JSONDecodeError, TypeError):
                    parsed = {}

                if parsed.get("requires_confirmation"):
                    self._emit("confirm_request", {
                        "session_id": session_id,
                        "tool_name": tool_name,
                        "reason": parsed.get("reason", ""),
                        "args": args,
                    })
                    result_msg = f"Tool '{tool_name}' requires user confirmation. Halting execution until confirmation received."
                    save_message(session_id, "assistant", result_msg)
                    return result_msg
                else:
                    result_msg = f"Tool '{tool_name}' result: {result}"

                self._emit("tool_result", {
                    "session_id": session_id,
                    "tool_name": tool_name,
                    "result": result,
                })

                contents.append({"role": "user", "text": result_msg})
                save_message(session_id, "user", "", tool_results=[{"tool": tool_name, "result": result}])
                continue

            save_message(session_id, "assistant", content)
            return content

        return "Max iterations reached."
