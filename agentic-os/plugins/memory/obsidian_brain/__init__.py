"""Obsidian Brain memory plugin — MemoryProvider interface.

Syncs agent memories bidirectionally with an Obsidian vault, creating
searchable, linkable markdown notes for persistent knowledge management.

Configuration
-------------
Secret (lives in $AGENTIC_OS_HOME/.env or the environment):
  OBSIDIAN_BRAIN_VAULT_PATH  — Path to the Obsidian vault (required)

Behavioral settings (live in $AGENTIC_OS_HOME/obsidian-brain.json):
  vault_path       — Vault directory path (overrides env var)
  auto_sync        — Auto-sync memories on every turn (default: true)
  journal_enabled  — Write daily journal entries (default: true)
  conversation_log — Log session summaries (default: true)
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.memory_provider import MemoryProvider
from tools.registry import tool_error

logger = logging.getLogger(__name__)

_PREFETCH_WAIT_SECS = 2


def _load_config() -> dict:
    from agentic_os_constants import get_agentic_os_home

    config = {
        "vault_path": os.environ.get("OBSIDIAN_BRAIN_VAULT_PATH", ""),
        "auto_sync": True,
        "journal_enabled": True,
        "conversation_log": True,
    }

    config_path = get_agentic_os_home() / "obsidian-brain.json"
    if config_path.exists():
        try:
            file_cfg = json.loads(config_path.read_text(encoding="utf-8"))
            config.update({k: v for k, v in file_cfg.items() if v is not None and v != ""})
        except Exception:
            pass

    return config


SEARCH_SCHEMA = {
    "name": "obsidian_search",
    "description": (
        "Search the Obsidian brain vault for notes, memories, and knowledge. "
        "Returns markdown notes ranked by relevance. Use this to recall past "
        "conversations, stored facts, project context, or any information "
        "previously saved to the Obsidian vault."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query."},
            "top_k": {"type": "integer", "description": "Max results (default: 10)."},
        },
        "required": ["query"],
    },
}

ADD_SCHEMA = {
    "name": "obsidian_add_memory",
    "description": (
        "Save a memory note to the Obsidian vault. Use this to persist "
        "important facts, decisions, preferences, or insights that should "
        "be recalled later. Creates a tagged markdown file in the vault."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "The memory content to store."},
            "tags": {"type": "string", "description": "Comma-separated tags for categorization."},
        },
        "required": ["content"],
    },
}

DELETE_SCHEMA = {
    "name": "obsidian_delete_memory",
    "description": (
        "Delete a memory note from the Obsidian vault by its filename. "
        "Use when stored information is obsolete or the user asks to forget it."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "memory_id": {"type": "string", "description": "Memory filename or ID to delete."},
        },
        "required": ["memory_id"],
    },
}

STATS_SCHEMA = {
    "name": "obsidian_stats",
    "description": (
        "Get statistics about the Obsidian brain vault — count of memories, "
        "conversations, journal entries, and vault location."
    ),
    "parameters": {"type": "object", "properties": {}},
}

JOURNAL_SCHEMA = {
    "name": "obsidian_journal",
    "description": (
        "Write a journal entry to the Obsidian vault. Use this to log "
        "daily activities, reflections, or notable events."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Journal entry content."},
        },
        "required": ["content"],
    },
}


class ObsidianBrainProvider(MemoryProvider):
    """Memory provider that syncs to an Obsidian vault as markdown notes."""

    def __init__(self):
        self._config = None
        self._vault = None
        self._vault_path = ""
        self._auto_sync = True
        self._journal_enabled = True
        self._conversation_log = True
        self._sync_thread = None
        self._sync_lock = threading.Lock()
        self._prefetch_thread = None
        self._prefetch_query = ""
        self._prefetch_result = ""
        self._prefetch_done = False
        self._prefetch_lock = threading.Lock()

    @property
    def name(self) -> str:
        return "obsidian-brain"

    def is_available(self) -> bool:
        cfg = _load_config()
        vault_path = cfg.get("vault_path", "")
        if not vault_path:
            return False
        return Path(vault_path).exists() or Path(vault_path).parent.exists()

    def save_config(self, values, agentic_os_home):
        config_path = Path(agentic_os_home) / "obsidian-brain.json"
        existing = {}
        if config_path.exists():
            try:
                existing = json.loads(config_path.read_text())
            except Exception:
                pass
        existing.update(values)
        config_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    def get_config_schema(self):
        return [
            {"key": "vault_path", "description": "Path to Obsidian vault directory", "required": True,
             "env_var": "OBSIDIAN_BRAIN_VAULT_PATH"},
            {"key": "auto_sync", "description": "Auto-sync memories each turn", "default": "true",
             "choices": ["true", "false"]},
            {"key": "journal_enabled", "description": "Enable daily journal entries", "default": "true",
             "choices": ["true", "false"]},
            {"key": "conversation_log", "description": "Log session summaries", "default": "true",
             "choices": ["true", "false"]},
        ]

    def initialize(self, session_id: str, **kwargs) -> None:
        self._config = _load_config()
        self._vault_path = self._config.get("vault_path", "")
        self._auto_sync = self._config.get("auto_sync", True)
        self._journal_enabled = self._config.get("journal_enabled", True)
        self._conversation_log = self._config.get("conversation_log", True)

        if not self._vault_path:
            logger.error("Obsidian Brain: No vault_path configured")
            return

        try:
            from ._vault import ObsidianVault
            self._vault = ObsidianVault(self._vault_path)
            logger.info("Obsidian Brain initialized: %s", self._vault_path)
        except Exception as e:
            logger.error("Obsidian Brain failed to initialize: %s", e)

    def system_prompt_block(self) -> str:
        if not self._vault:
            return ""
        stats = self._vault.get_vault_stats()
        return (
            "# Obsidian Brain\n"
            f"Active. Vault: {self._vault_path}\n"
            f"Stats: {stats['memories']} memories, {stats['conversations']} conversations, "
            f"{stats['journal_entries']} journal entries\n"
            "You have a persistent Obsidian vault for knowledge management. "
            "Use obsidian_search to recall information, obsidian_add_memory to store facts, "
            "obsidian_journal for daily logs, and obsidian_stats for vault status.\n"
            "All memories are stored as markdown notes with frontmatter metadata."
        )

    def on_turn_start(self, turn_number: int, message: str, **kwargs) -> None:
        if self._vault and self._journal_enabled and turn_number == 1:
            try:
                self._vault.write_journal_entry(f"Session started. User message: {message[:200]}")
            except Exception as e:
                logger.debug("Obsidian journal write failed: %s", e)

    def sync_turn(self, user_content: str, assistant_content: str, *,
                  session_id: str = "", messages: Optional[List[Dict[str, Any]]] = None) -> None:
        if not self._vault or not self._auto_sync:
            return

        def _sync():
            try:
                if len(user_content) > 20:
                    self._vault.write_memory(
                        f"turn_{session_id[:8]}",
                        f"User: {user_content}\n\nAssistant: {assistant_content}",
                        metadata={"session_id": session_id, "write_origin": "auto_sync"}
                    )
            except Exception as e:
                logger.debug("Obsidian sync failed: %s", e)

        with self._sync_lock:
            if self._sync_thread and self._sync_thread.is_alive():
                self._sync_thread.join(timeout=3.0)
            self._sync_thread = threading.Thread(target=_sync, daemon=True, name="obsidian-sync")
            self._sync_thread.start()

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        if not self._vault or not self._conversation_log:
            return
        try:
            summary_parts = []
            for msg in messages[-6:]:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if isinstance(content, str) and content:
                    summary_parts.append(f"**{role}**: {content[:200]}")
            if summary_parts:
                summary = "\n\n".join(summary_parts)
                self._vault.write_conversation_summary(
                    messages[0].get("session_id", "unknown") if messages else "unknown",
                    summary,
                    turn_count=len(messages)
                )
        except Exception as e:
            logger.debug("Obsidian session end failed: %s", e)

    def on_memory_write(self, action: str, target: str, content: str,
                        metadata: Optional[Dict[str, Any]] = None) -> None:
        if not self._vault or action != "add":
            return
        try:
            self._vault.write_memory(
                f"builtin_{hash(content) % 100000}",
                content,
                metadata=metadata or {}
            )
        except Exception as e:
            logger.debug("Obsidian memory mirror failed: %s", e)

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [SEARCH_SCHEMA, ADD_SCHEMA, DELETE_SCHEMA, STATS_SCHEMA, JOURNAL_SCHEMA]

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs) -> str:
        if not self._vault:
            return json.dumps({"error": "Obsidian Brain not initialized. Check vault_path config."})

        import hashlib

        if tool_name == "obsidian_search":
            query = args.get("query", "")
            if not query:
                return tool_error("Missing required parameter: query")
            try:
                top_k = max(1, min(int(args.get("top_k", 10)), 50))
                results = self._vault.search_memories(query, top_k=top_k)
                if not results:
                    return json.dumps({"result": "No matching notes found in Obsidian vault.", "query": query})
                return json.dumps({"results": results, "count": len(results), "query": query})
            except Exception as e:
                return tool_error(f"Search failed: {e}")

        elif tool_name == "obsidian_add_memory":
            content = args.get("content", "")
            if not content:
                return tool_error("Missing required parameter: content")
            try:
                tags_str = args.get("tags", "")
                metadata = {"write_origin": "tool_call"}
                if tags_str:
                    metadata["tags"] = [t.strip() for t in tags_str.split(",")]
                memory_id = hashlib.sha256(content.encode()).hexdigest()[:16]
                filepath = self._vault.write_memory(memory_id, content, metadata=metadata)
                return json.dumps({"result": "Memory saved to Obsidian vault.", "file": filepath, "id": memory_id})
            except Exception as e:
                return tool_error(f"Failed to save: {e}")

        elif tool_name == "obsidian_delete_memory":
            memory_id = args.get("memory_id", "")
            if not memory_id:
                return tool_error("Missing required parameter: memory_id")
            try:
                deleted = self._vault.delete_memory(memory_id)
                if deleted:
                    return json.dumps({"result": "Memory deleted.", "id": memory_id})
                return json.dumps({"error": f"No memory found with id: {memory_id}"})
            except Exception as e:
                return tool_error(f"Delete failed: {e}")

        elif tool_name == "obsidian_stats":
            try:
                stats = self._vault.get_vault_stats()
                return json.dumps(stats)
            except Exception as e:
                return tool_error(f"Stats failed: {e}")

        elif tool_name == "obsidian_journal":
            content = args.get("content", "")
            if not content:
                return tool_error("Missing required parameter: content")
            try:
                self._vault.write_journal_entry(content)
                return json.dumps({"result": "Journal entry saved."})
            except Exception as e:
                return tool_error(f"Journal write failed: {e}")

        return tool_error(f"Unknown tool: {tool_name}")

    def shutdown(self) -> None:
        for t in (self._sync_thread, self._prefetch_thread):
            if t and t.is_alive():
                t.join(timeout=5.0)


def register(ctx) -> None:
    """Register Obsidian Brain as a memory provider plugin."""
    ctx.register_memory_provider(ObsidianBrainProvider())
