"""Thin wrapper over the Anthropic Messages API: structured JSON out, usage and cost in.

Everything that talks to the API goes through `call_json` so cost and latency are
measured the same way for label drafting and for the baseline.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import anthropic
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_MODEL = "claude-opus-5"

# USD per million tokens. Cache writes are 1.25x base input (5-minute TTL), cache
# reads 0.1x. Update alongside any model change.
PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


@dataclass
class Usage:
    """Token counts and derived cost for one or many calls."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    calls: int = 0
    latencies_s: list[float] = field(default_factory=list)

    def add(self, other: Usage) -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_creation_input_tokens += other.cache_creation_input_tokens
        self.cache_read_input_tokens += other.cache_read_input_tokens
        self.calls += other.calls
        self.latencies_s.extend(other.latencies_s)

    def cost_usd(self, model: str) -> float:
        if model not in PRICING_PER_MTOK:
            return float("nan")
        in_rate, out_rate = PRICING_PER_MTOK[model]
        return (
            self.input_tokens * in_rate
            + self.cache_creation_input_tokens * in_rate * 1.25
            + self.cache_read_input_tokens * in_rate * 0.10
            + self.output_tokens * out_rate
        ) / 1_000_000

    def summary(self, model: str) -> dict:
        lat = sorted(self.latencies_s)
        n = len(lat)

        def pct(p: float) -> float | None:
            if not n:
                return None
            return round(lat[min(n - 1, int(p * n))], 2)

        total = self.cost_usd(model)
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "total_cost_usd": round(total, 4),
            "cost_per_ticket_usd": round(total / self.calls, 6) if self.calls else None,
            "latency_mean_s": round(sum(lat) / n, 2) if n else None,
            "latency_p50_s": pct(0.50),
            "latency_p95_s": pct(0.95),
        }


def get_client() -> anthropic.Anthropic:
    """Build a client, loading .env first. Key comes from the environment only."""
    load_dotenv(REPO_ROOT / ".env")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit(
            "ANTHROPIC_API_KEY is not set.\n"
            "Copy .env.example to .env and put your key in it, or export the variable."
        )
    return anthropic.Anthropic(max_retries=4)


def call_json(
    client: anthropic.Anthropic,
    *,
    model: str,
    system: str,
    user: str,
    json_schema: dict,
    effort: str = "high",
    max_tokens: int = 4000,
) -> tuple[dict, Usage]:
    """One request returning schema-valid JSON, plus its usage.

    The system prompt carries a cache breakpoint: it is identical across every ticket
    in a run, so after the first call it is served from cache.
    """
    started = time.perf_counter()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=[
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user}],
        output_config={
            "effort": effort,
            "format": {"type": "json_schema", "schema": json_schema},
        },
    )
    elapsed = time.perf_counter() - started

    if response.stop_reason == "refusal":
        raise RuntimeError(f"Request refused: {response.stop_details}")

    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise RuntimeError(f"No text block in response (stop_reason={response.stop_reason})")

    usage = Usage(
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cache_creation_input_tokens=response.usage.cache_creation_input_tokens or 0,
        cache_read_input_tokens=response.usage.cache_read_input_tokens or 0,
        calls=1,
        latencies_s=[elapsed],
    )
    return json.loads(text), usage
