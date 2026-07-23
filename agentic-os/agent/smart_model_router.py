"""
Smart Model Router & Cost Intelligence Engine for Agentic OS
=============================================================
Provides intelligent task-complexity classification, dynamic model tier routing,
token budget tracking, cache-aware routing, and graceful fallback chains.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

# Standard Model Pricing Table (USD per 1,000 tokens)
MODEL_PRICING_PER_1K: Dict[str, Dict[str, float]] = {
    "gpt-4o": {"input": 0.0025, "output": 0.0100},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "claude-3-5-sonnet": {"input": 0.0030, "output": 0.0150},
    "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
    "deepseek-chat": {"input": 0.00014, "output": 0.00028},
    "ollama/llama3": {"input": 0.0, "output": 0.0},
    "local": {"input": 0.0, "output": 0.0},
}


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
            r"\brefactor\b", r"\barchitect\b", r"\bdebug\b", r"\bbenchmark\b",
            r"\boptimize\b", r"\bproof\b", r"\btheorem\b", r"\bsecurity audit\b",
            r"\bvulnerability\b", r"\bmulti-step\b"
        ]
        indicators_simple = [r"\bhi\b", r"\bhello\b", r"\bthanks\b", r"\bstatus\b", r"\bversion\b", r"\bwho are you\b"]

        complex_matches = sum(1 for kw in indicators_complex if re.search(kw, text))
        simple_matches = sum(1 for kw in indicators_simple if re.search(kw, text))

        if word_count < 30 and simple_matches > 0 and complex_matches == 0:
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

    def calculate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimates cost in USD based on token counts and model pricing."""
        rates = MODEL_PRICING_PER_1K.get(model, {"input": 0.0015, "output": 0.0030})
        cost = (prompt_tokens / 1000.0 * rates["input"]) + (completion_tokens / 1000.0 * rates["output"])
        return round(cost, 6)

    def record_usage(self, model: str, prompt_tokens: int, completion_tokens: int, cost_usd: Optional[float] = None):
        """Records token spend for analytics and budget tracking."""
        if cost_usd is None:
            cost_usd = self.calculate_cost(model, prompt_tokens, completion_tokens)

        today = time.strftime("%Y-%m-%d")
        if "daily_spend" not in self.usage_data:
            self.usage_data["daily_spend"] = {}
        self.usage_data["daily_spend"][today] = round(self.usage_data["daily_spend"].get(today, 0.0) + cost_usd, 6)

        record = {
            "timestamp": time.time(),
            "date": today,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": cost_usd,
        }
        self.usage_data.setdefault("records", []).append(record)
        self._save_usage()
