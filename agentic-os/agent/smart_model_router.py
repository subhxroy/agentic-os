"""
Smart Model Router & Cost Intelligence Engine for Agentic OS
=============================================================
Provides intelligent task-complexity classification, dynamic model tier routing,
token budget tracking, cache-aware routing, and graceful fallback chains.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Any, Optional


class SmartModelRouter:
    """
    Intelligent Model Router & Budget Manager.
    """

    def __init__(
        self,
        daily_budget_usd: float = 10.0,
        storage_dir: Optional[Path] = None,
    ):
        self.daily_budget_usd = daily_budget_usd
        if storage_dir is None:
            storage_dir = Path.home() / ".agentic_os" / "cost_router"
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.usage_file = self.storage_dir / "token_spend.json"
        self._load_usage()

    def _load_usage(self):
        if self.usage_file.exists():
            try:
                self.usage_data = json.loads(self.usage_file.read_text(encoding="utf-8"))
            except Exception:
                self.usage_data = {"daily_spend": {}, "records": []}
        else:
            self.usage_data = {"daily_spend": {}, "records": []}

    def _save_usage(self):
        self.usage_file.write_text(json.dumps(self.usage_data, indent=2), encoding="utf-8")

    def classify_task_complexity(self, prompt: str, system_prompt: str = "", tools_count: int = 0) -> str:
        """
        Classifies task complexity into:
          - 'simple' (greetings, simple Q&A, basic formatting)
          - 'moderate' (data analysis, single file edits, standard web queries)
          - 'complex' (multi-file refactoring, deep research, mathematical reasoning)
        """
        text = f"{system_prompt} {prompt}".lower()
        word_count = len(text.split())

        indicators_complex = [
            "refactor", "architect", "debug", "benchmark", "optimize",
            "proof", "theorem", "multi-step", "security audit", "vulnerability"
        ]
        indicators_simple = ["hi", "hello", "thanks", "status", "version", "help", "who are you"]

        complex_matches = sum(1 for kw in indicators_complex if kw in text)

        if word_count < 30 and any(s in text for s in indicators_simple) and complex_matches == 0:
            return "simple"
        elif complex_matches >= 2 or word_count > 400 or tools_count > 15:
            return "complex"
        else:
            return "moderate"

    def select_model(
        self,
        prompt: str,
        preferred_model: str = "auto",
        available_models: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Dynamically routes task to the best model tier considering complexity, budget, and availability.
        """
        if available_models is None:
            available_models = ["ollama/llama3", "gpt-4o-mini", "claude-3-5-sonnet"]

        today = time.strftime("%Y-%m-%d")
        current_daily_spend = self.usage_data.get("daily_spend", {}).get(today, 0.0)

        complexity = self.classify_task_complexity(prompt)

        if preferred_model != "auto":
            return {
                "selected_model": preferred_model,
                "complexity": complexity,
                "reason": "User specified explicit model preference.",
                "fallback_chain": [m for m in available_models if m != preferred_model],
            }

        # Budget enforcement: fallback to local if near daily limit
        if current_daily_spend >= self.daily_budget_usd:
            selected = "ollama/llama3" if "ollama/llama3" in available_models else available_models[0]
            reason = "Daily budget threshold reached; routed to local/cost-effective model."
        elif complexity == "simple":
            selected = "ollama/llama3" if "ollama/llama3" in available_models else available_models[0]
            reason = "Task classified as simple; selected tier-1 fast model."
        elif complexity == "moderate":
            selected = "gpt-4o-mini" if "gpt-4o-mini" in available_models else available_models[0]
            reason = "Task classified as moderate; selected tier-2 general model."
        else:
            selected = "claude-3-5-sonnet" if "claude-3-5-sonnet" in available_models else available_models[-1]
            reason = "Task classified as complex; selected tier-3 frontier model."

        fallback_chain = [m for m in available_models if m != selected]
        return {
            "selected_model": selected,
            "complexity": complexity,
            "reason": reason,
            "fallback_chain": fallback_chain,
            "daily_spend_usd": current_daily_spend,
            "daily_budget_usd": self.daily_budget_usd,
        }

    def record_usage(self, model: str, prompt_tokens: int, completion_tokens: int, estimated_cost_usd: float):
        """Records token spend for analytics and budget tracking."""
        today = time.strftime("%Y-%m-%d")
        if "daily_spend" not in self.usage_data:
            self.usage_data["daily_spend"] = {}
        self.usage_data["daily_spend"][today] = self.usage_data["daily_spend"].get(today, 0.0) + estimated_cost_usd

        record = {
            "timestamp": time.time(),
            "date": today,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": estimated_cost_usd,
        }
        self.usage_data.setdefault("records", []).append(record)
        self._save_usage()
