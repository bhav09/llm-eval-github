"""Token cost calculation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from config import ROOT_DIR

PRICING_PATH = ROOT_DIR / "config" / "models_pricing.json"


@dataclass(frozen=True)
class CostBreakdown:
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    cost_usd: float
    cache_savings_usd: float


def load_pricing() -> dict:
    return json.loads(PRICING_PATH.read_text(encoding="utf-8"))


def get_model_rates(model: str, pricing: dict | None = None) -> dict:
    pricing = pricing or load_pricing()
    return pricing.get(model, pricing.get("default", {}))


def compute_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int = 0,
    pricing: dict | None = None,
) -> CostBreakdown:
    rates = get_model_rates(model, pricing)
    in_rate = rates.get("input_per_million", 0.30)
    out_rate = rates.get("output_per_million", 0.60)
    cached_rate = rates.get("cached_input_per_million", in_rate * 0.5)

    billable_input = max(0, prompt_tokens - cached_tokens)
    cost = (billable_input * in_rate + cached_tokens * cached_rate + completion_tokens * out_rate) / 1_000_000
    cost_without_cache = (prompt_tokens * in_rate + completion_tokens * out_rate) / 1_000_000
    savings = max(0.0, cost_without_cache - cost)

    return CostBreakdown(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_tokens=cached_tokens,
        cost_usd=cost,
        cache_savings_usd=savings,
    )
