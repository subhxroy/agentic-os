import os
import json
import time
import logging
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

class Provider(Enum):
    GEMINI = "gemini"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"

@dataclass
class ModelConfig:
    provider: Provider
    model_id: str
    cost_per_1k_input: float   # USD per 1K input tokens
    cost_per_1k_output: float  # USD per 1K output tokens
    max_tokens: int = 4096
    tier: str = "standard"     # cheap, standard, premium

@dataclass
class UsageRecord:
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    success: bool
    timestamp: float = field(default_factory=time.time)

# Predefined model catalog
MODEL_CATALOG = {
    # Gemini models (cheap tier)
    "gemini-3.5-flash": ModelConfig(Provider.GEMINI, "gemini-3.5-flash", 0.000075, 0.0003, tier="cheap"),
    "gemini-2.5-flash-lite": ModelConfig(Provider.GEMINI, "gemini-2.5-flash-lite", 0.000075, 0.0003, tier="cheap"),
    "gemini-2.0-flash": ModelConfig(Provider.GEMINI, "gemini-2.0-flash", 0.000075, 0.0003, tier="cheap"),
    "gemini-2.5-flash": ModelConfig(Provider.GEMINI, "gemini-2.5-flash", 0.00015, 0.0006, tier="standard"),
    "gemini-2.5-pro": ModelConfig(Provider.GEMINI, "gemini-2.5-pro", 0.00125, 0.01, tier="premium"),
    # OpenAI models
    "gpt-4o-mini": ModelConfig(Provider.OPENAI, "gpt-4o-mini", 0.00015, 0.0006, tier="cheap"),
    "gpt-4o": ModelConfig(Provider.OPENAI, "gpt-4o", 0.0025, 0.01, tier="standard"),
    "gpt-4.1": ModelConfig(Provider.OPENAI, "gpt-4.1", 0.002, 0.008, tier="standard"),
    # Anthropic models
    "claude-sonnet-4-20250514": ModelConfig(Provider.ANTHROPIC, "claude-sonnet-4-20250514", 0.003, 0.015, tier="standard"),
    "claude-haiku-3.5": ModelConfig(Provider.ANTHROPIC, "claude-haiku-3.5", 0.0008, 0.004, tier="cheap"),
}

# Tier routing: which models to try in order
TIER_CHAINS = {
    "cost_optimized": ["gemini-3.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash", "gpt-4o-mini", "claude-haiku-3.5"],
    "balanced": ["gemini-2.5-flash", "gemini-2.5-pro", "gpt-4o", "claude-sonnet-4-20250514"],
    "quality_first": ["gemini-2.5-pro", "gpt-4o", "claude-sonnet-4-20250514"],
}

class ModelRouter:
    def __init__(self):
        self._clients = {}
        self._usage_log: list[UsageRecord] = []
        self._daily_cost = 0.0
        self._daily_budget = float(os.environ.get("DAILY_BUDGET_USD", "10.0"))
        self._init_clients()

    def _init_clients(self):
        """Initialize provider clients based on available API keys."""
        # Gemini
        gemini_key = os.environ.get("GEMINI_API_KEY")
        if gemini_key:
            import google.genai as genai
            self._clients[Provider.GEMINI] = genai.Client(api_key=gemini_key)

        # OpenAI
        openai_key = os.environ.get("OPENAI_API_KEY")
        if openai_key:
            try:
                import openai
                self._clients[Provider.OPENAI] = openai.OpenAI(api_key=openai_key)
            except ImportError:
                logger.warning("openai package not installed, skipping OpenAI provider")

        # Anthropic
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        if anthropic_key:
            try:
                import anthropic
                self._clients[Provider.ANTHROPIC] = anthropic.Anthropic(api_key=anthropic_key)
            except ImportError:
                logger.warning("anthropic package not installed, skipping Anthropic provider")

        logger.info(f"Model Router initialized with providers: {[p.value for p in self._clients.keys()]}")

    def _check_budget(self) -> bool:
        """Check if we're within daily budget."""
        return self._daily_cost < self._daily_budget

    def _estimate_cost(self, config: ModelConfig, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost in USD for a request."""
        return (input_tokens * config.cost_per_1k_input + output_tokens * config.cost_per_1k_output) / 1000

    def select_model(self, tier: str = "cost_optimized", exclude: list[str] = None) -> Optional[str]:
        """Select the best available model based on tier and budget."""
        exclude = exclude or []
        chain = TIER_CHAINS.get(tier, TIER_CHAINS["cost_optimized"])

        for model_id in chain:
            if model_id in exclude:
                continue
            config = MODEL_CATALOG.get(model_id)
            if not config:
                continue
            if config.provider not in self._clients:
                continue
            if not self._check_budget() and config.tier != "cheap":
                continue
            return model_id
        return None

    def generate_content(self, system_instruction: str, contents: list,
                         tier: str = "cost_optimized", max_retries: int = 3) -> dict:
        """Generate content with automatic fallback and retry logic."""
        exclude = []
        last_error = None

        for attempt in range(max_retries):
            model_id = self.select_model(tier=tier, exclude=exclude)
            if not model_id:
                return {"error": "No available models", "text": "", "model": None}

            config = MODEL_CATALOG[model_id]
            start = time.time()

            try:
                result = self._call_provider(config, system_instruction, contents)
                latency = (time.time() - start) * 1000

                # Track usage
                input_tokens = result.get("input_tokens", 0)
                output_tokens = result.get("output_tokens", 0)
                cost = self._estimate_cost(config, input_tokens, output_tokens)
                self._daily_cost += cost

                record = UsageRecord(
                    provider=config.provider.value,
                    model=model_id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost,
                    latency_ms=latency,
                    success=True
                )
                self._usage_log.append(record)

                logger.info(f"Model {model_id}: {output_tokens} tokens, ${cost:.6f}, {latency:.0f}ms")
                return {
                    "text": result["text"],
                    "model": model_id,
                    "provider": config.provider.value,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost_usd": cost,
                    "latency_ms": latency,
                }

            except Exception as e:
                latency = (time.time() - start) * 1000
                last_error = e
                exclude.append(model_id)
                logger.warning(f"Model {model_id} failed: {e}")

                record = UsageRecord(
                    provider=config.provider.value,
                    model=model_id,
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=0,
                    latency_ms=latency,
                    success=False
                )
                self._usage_log.append(record)

        return {"error": f"All models failed: {last_error}", "text": "", "model": None}

    def _call_provider(self, config: ModelConfig, system_instruction: str, contents: list) -> dict:
        """Call the appropriate provider's API."""
        if config.provider == Provider.GEMINI:
            return self._call_gemini(config, system_instruction, contents)
        elif config.provider == Provider.OPENAI:
            return self._call_openai(config, system_instruction, contents)
        elif config.provider == Provider.ANTHROPIC:
            return self._call_anthropic(config, system_instruction, contents)
        raise ValueError(f"Unknown provider: {config.provider}")

    def _call_gemini(self, config: ModelConfig, system_instruction: str, contents: list) -> dict:
        from google.genai import types
        client = self._clients[Provider.GEMINI]
        formatted_contents = []
        for item in contents:
            if isinstance(item, dict):
                role = item.get("role", "user")
                text = item.get("text", "")
                formatted_contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=text)]
                    )
                )
            else:
                formatted_contents.append(item)
        response = client.models.generate_content(
            model=config.model_id,
            contents=formatted_contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                max_output_tokens=config.max_tokens,
            ),
        )
        input_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) or 0
        output_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) or 0
        return {
            "text": response.text or "",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }

    def _call_openai(self, config: ModelConfig, system_instruction: str, contents: list) -> dict:
        client = self._clients[Provider.OPENAI]
        messages = [{"role": "system", "content": system_instruction}]
        for content in contents:
            if isinstance(content, dict):
                role = content.get("role", "user")
                text = content.get("text", "")
            else:
                role = getattr(content, 'role', 'user')
                text = content.parts[0].text if hasattr(content, 'parts') else str(content)
            messages.append({"role": role if role in ("user", "assistant") else "user", "content": text})

        response = client.chat.completions.create(
            model=config.model_id,
            messages=messages,
            max_tokens=config.max_tokens,
        )
        return {
            "text": response.choices[0].message.content or "",
            "input_tokens": response.usage.prompt_tokens if response.usage else 0,
            "output_tokens": response.usage.completion_tokens if response.usage else 0,
        }

    def _call_anthropic(self, config: ModelConfig, system_instruction: str, contents: list) -> dict:
        client = self._clients[Provider.ANTHROPIC]
        messages = []
        for content in contents:
            if isinstance(content, dict):
                role = content.get("role", "user")
                text = content.get("text", "")
            else:
                role = getattr(content, 'role', 'user')
                text = content.parts[0].text if hasattr(content, 'parts') else str(content)
            messages.append({"role": role if role in ("user", "assistant") else "user", "content": text})

        response = client.messages.create(
            model=config.model_id,
            max_tokens=config.max_tokens,
            system=system_instruction,
            messages=messages,
        )
        return {
            "text": response.content[0].text if response.content else "",
            "input_tokens": response.usage.input_tokens if response.usage else 0,
            "output_tokens": response.usage.output_tokens if response.usage else 0,
        }

    def get_usage_stats(self) -> dict:
        """Get aggregated usage statistics."""
        total_cost = sum(r.cost_usd for r in self._usage_log)
        by_provider = {}
        for r in self._usage_log:
            if r.provider not in by_provider:
                by_provider[r.provider] = {"requests": 0, "cost": 0, "tokens": 0}
            by_provider[r.provider]["requests"] += 1
            by_provider[r.provider]["cost"] += r.cost_usd
            by_provider[r.provider]["tokens"] += r.input_tokens + r.output_tokens

        return {
            "total_cost_usd": round(total_cost, 6),
            "daily_budget_usd": self._daily_budget,
            "daily_remaining_usd": round(self._daily_budget - self._daily_cost, 6),
            "total_requests": len(self._usage_log),
            "by_provider": by_provider,
            "available_providers": [p.value for p in self._clients.keys()],
        }
