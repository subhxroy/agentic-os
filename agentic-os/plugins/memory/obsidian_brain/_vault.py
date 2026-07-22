"""Obsidian vault sync backend — writes memories as markdown notes."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ObsidianVault:
    """Manages reading/writing memories to an Obsidian vault as markdown files."""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        self.memories_dir = self.vault_path / "memories"
        self.conversations_dir = self.vault_path / "conversations"
        self.journal_dir = self.vault_path / "journal"
        self._ensure_dirs()

    def _ensure_dirs(self):
        for d in [self.memories_dir, self.conversations_dir, self.journal_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def _safe_filename(self, text: str, max_len: int = 80) -> str:
        safe = re.sub(r'[<>:"/\\|?*]', '', text)
        safe = re.sub(r'\s+', '-', safe.strip())
        return safe[:max_len] if safe else "untitled"

    def _content_hash(self, content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()[:12]

    def write_memory(self, memory_id: str, content: str, metadata: Optional[Dict] = None) -> str:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        safe_name = self._safe_filename(content[:60])
        filename = f"{safe_name}_{memory_id[:8]}.md"
        filepath = self.memories_dir / filename

        tags = []
        if metadata:
            if metadata.get("channel"):
                tags.append(f"channel/{metadata['channel']}")
            if metadata.get("write_origin"):
                tags.append(f"origin/{metadata['write_origin']}")

        frontmatter = {
            "id": memory_id,
            "created": ts,
            "updated": ts,
            "type": "memory",
            "tags": tags,
        }

        if metadata:
            for k, v in metadata.items():
                if k not in ("channel", "write_origin") and isinstance(v, (str, int, float, bool)):
                    frontmatter[k] = v

        fm_yaml = "---\n"
        for k, v in frontmatter.items():
            if isinstance(v, list):
                fm_yaml += f"{k}:\n"
                for item in v:
                    fm_yaml += f"  - {item}\n"
            else:
                fm_yaml += f"{k}: \"{v}\"\n"
        fm_yaml += "---\n\n"

        body = f"# {content[:80]}\n\n{content}\n"
        filepath.write_text(fm_yaml + body, encoding="utf-8")
        return str(filepath)

    def read_all_memories(self) -> List[Dict[str, Any]]:
        memories = []
        for fp in self.memories_dir.glob("*.md"):
            try:
                text = fp.read_text(encoding="utf-8")
                content, meta = self._parse_note(text)
                meta["file"] = str(fp)
                meta["content"] = content
                memories.append(meta)
            except Exception as e:
                logger.debug("Failed to read %s: %s", fp, e)
        return memories

    def search_memories(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        all_memories = self.read_all_memories()
        query_lower = query.lower()
        scored = []
        for m in all_memories:
            content = m.get("content", "").lower()
            score = 0
            for word in query_lower.split():
                if word in content:
                    score += content.count(word)
            if score > 0:
                scored.append((score, m))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [{"memory": m.get("content", ""), "score": s, "id": m.get("id", ""), "file": m.get("file", "")}
                for s, m in scored[:top_k]]

    def delete_memory(self, memory_id: str) -> bool:
        for fp in self.memories_dir.glob("*.md"):
            try:
                text = fp.read_text(encoding="utf-8")
                if memory_id in text:
                    fp.unlink()
                    return True
            except Exception:
                continue
        return False

    def write_conversation_summary(self, session_id: str, summary: str, turn_count: int = 0):
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"session_{ts}_{session_id[:8]}.md"
        filepath = self.conversations_dir / filename

        frontmatter = f"---\nsession_id: \"{session_id}\"\ntimestamp: \"{ts}\"\nturns: {turn_count}\ntype: conversation\n---\n\n"
        body = f"# Session {session_id[:8]}\n\n{summary}\n"
        filepath.write_text(frontmatter + body, encoding="utf-8")

    def write_journal_entry(self, content: str):
        today = datetime.now().strftime("%Y-%m-%d")
        filepath = self.journal_dir / f"{today}.md"

        if filepath.exists():
            existing = filepath.read_text(encoding="utf-8")
            ts = datetime.now().strftime("%H:%M:%S")
            filepath.write_text(existing + f"\n\n## {ts}\n\n{content}\n", encoding="utf-8")
        else:
            frontmatter = f"---\ndate: \"{today}\"\ntype: journal\n---\n\n"
            body = f"# {today}\n\n## {datetime.now().strftime('%H:%M:%S')}\n\n{content}\n"
            filepath.write_text(frontmatter + body, encoding="utf-8")

    def _parse_note(self, text: str) -> tuple:
        meta = {}
        content = text
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                fm_text = parts[1].strip()
                content = parts[2].strip()
                for line in fm_text.split("\n"):
                    if ":" in line:
                        key, val = line.split(":", 1)
                        val = val.strip().strip('"').strip("'")
                        if val.startswith("["):
                            val = [v.strip().strip('"').strip("'") for v in val.strip("[]").split(",")]
                        meta[key.strip()] = val
        return content, meta

    def get_vault_stats(self) -> Dict[str, Any]:
        return {
            "memories": len(list(self.memories_dir.glob("*.md"))),
            "conversations": len(list(self.conversations_dir.glob("*.md"))),
            "journal_entries": len(list(self.journal_dir.glob("*.md"))),
            "vault_path": str(self.vault_path),
        }
