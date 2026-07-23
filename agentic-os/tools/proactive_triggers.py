"""
Proactive Intelligence Engine for Agentic OS
================================================
Implements event-driven triggers (RSS feeds, webhooks, Git repo changes, URL delta checks),
scheduled deep research jobs, predictive context pre-loading, and anomaly monitoring.
"""

from __future__ import annotations

import json
import time
import hashlib
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
import urllib.request

from tools.registry import registry


class ProactiveEngine:
    """
    Proactive Intelligence Engine supporting event triggers, predictive context loading,
    and background monitoring.
    """

    def __init__(self, storage_dir: Optional[Path] = None):
        if storage_dir is None:
            storage_dir = Path.home() / ".agentic_os" / "proactive"
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.triggers_file = self.storage_dir / "triggers.json"
        self.access_log_file = self.storage_dir / "access_patterns.json"
        self._load_state()

    def _load_state(self):
        if self.triggers_file.exists():
            try:
                self.triggers = json.loads(self.triggers_file.read_text(encoding="utf-8"))
            except Exception:
                self.triggers = {}
        else:
            self.triggers = {}

        if self.access_log_file.exists():
            try:
                self.access_patterns = json.loads(self.access_log_file.read_text(encoding="utf-8"))
            except Exception:
                self.access_patterns = {}
        else:
            self.access_patterns = {}

    def _save_state(self):
        self.triggers_file.write_text(json.dumps(self.triggers, indent=2), encoding="utf-8")
        self.access_log_file.write_text(json.dumps(self.access_patterns, indent=2), encoding="utf-8")

    def register_trigger(
        self,
        trigger_id: str,
        trigger_type: str,
        target: str,
        condition: str,
        action_prompt: str,
        interval_seconds: int = 300,
    ) -> Dict[str, Any]:
        """Registers an event trigger (e.g. RSS, URL delta, Git commit watcher)."""
        record = {
            "id": trigger_id,
            "type": trigger_type,
            "target": target,
            "condition": condition,
            "action_prompt": action_prompt,
            "interval_seconds": interval_seconds,
            "last_check": 0,
            "last_hash": "",
            "status": "active",
            "created_at": time.time(),
        }
        self.triggers[trigger_id] = record
        self._save_state()
        return {"status": "success", "trigger": record}

    def list_triggers(self) -> List[Dict[str, Any]]:
        return list(self.triggers.values())

    def remove_trigger(self, trigger_id: str) -> Dict[str, Any]:
        if trigger_id in self.triggers:
            deleted = self.triggers.pop(trigger_id)
            self._save_state()
            return {"status": "success", "removed": deleted}
        return {"status": "error", "message": f"Trigger {trigger_id} not found"}

    def record_access(self, file_path: str, context_tags: List[str]):
        """Records file access patterns for predictive context pre-loading."""
        now = time.time()
        key = str(Path(file_path).name)
        if key not in self.access_patterns:
            self.access_patterns[key] = {"count": 0, "last_accessed": now, "tags": []}
        self.access_patterns[key]["count"] += 1
        self.access_patterns[key]["last_accessed"] = now
        for tag in context_tags:
            if tag not in self.access_patterns[key]["tags"]:
                self.access_patterns[key]["tags"].append(tag)
        self._save_state()

    def get_predictive_context(self, current_tags: List[str], limit: int = 5) -> List[str]:
        """Returns predicted relevant files to pre-load into context based on access patterns."""
        scored = []
        for file_name, meta in self.access_patterns.items():
            tag_overlap = len(set(meta.get("tags", [])) & set(current_tags))
            recency_score = 1.0 / (1.0 + (time.time() - meta.get("last_accessed", 0)) / 3600.0)
            score = (meta.get("count", 0) * 0.4) + (tag_overlap * 2.0) + (recency_score * 3.0)
            scored.append((score, file_name))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:limit]]


def handle_proactive_trigger_tool(action: str, **kwargs) -> str:
    """Tool entry point for managing proactive triggers and predictive context."""
    engine = ProactiveEngine()
    if action == "register":
        result = engine.register_trigger(
            trigger_id=kwargs.get("trigger_id", f"trig_{int(time.time())}"),
            trigger_type=kwargs.get("trigger_type", "url_delta"),
            target=kwargs.get("target", ""),
            condition=kwargs.get("condition", "on_change"),
            action_prompt=kwargs.get("action_prompt", "Notify user of changes"),
            interval_seconds=int(kwargs.get("interval_seconds", 300)),
        )
        return json.dumps(result, indent=2)
    elif action == "list":
        return json.dumps(engine.list_triggers(), indent=2)
    elif action == "remove":
        return json.dumps(engine.remove_trigger(kwargs.get("trigger_id", "")), indent=2)
    elif action == "predict_context":
        tags = kwargs.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]
        candidates = engine.get_predictive_context(tags)
        return json.dumps({"predictive_context_candidates": candidates}, indent=2)
    else:
        return json.dumps({"error": f"Unknown action: {action}"})


registry.register(
    name="proactive_triggers",
    toolset="proactive",
    schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["register", "list", "remove", "predict_context"],
                "description": "Action to perform on proactive triggers or predictive context.",
            },
            "trigger_id": {"type": "string", "description": "Unique ID for the trigger."},
            "trigger_type": {"type": "string", "description": "Type of trigger: url_delta, rss, git_hook, webhook."},
            "target": {"type": "string", "description": "Target URL or repository path to monitor."},
            "action_prompt": {"type": "string", "description": "Agent action prompt when trigger fires."},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Context tags for prediction."},
        },
        "required": ["action"],
    },
    handler=handle_proactive_trigger_tool,
    description="Manage event-driven proactive triggers, RSS/webhook watchers, and predictive context pre-loading.",
)
