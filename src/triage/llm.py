"""Thin wrapper over the OpenAI Responses API: structured JSON out, usage and cost in.

Everything that talks to the model goes through `call_json`, so cost and latency are
measured the same way for label drafting and for the baseline. That seam is what made
swapping providers a single-file change; it is deliberately not a plugin framework.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

REPO_ROOT = Path(__file__).resolve().parents[2]

# Override for a whole run with TRIAGE_MODEL, or per command with --model.
DEFAULT_MODEL = os.environ.get("TRIAGE_MODEL", "gpt-6-astra")

# USD per million tokens: (uncached input, cached input, output).
#
# Source: https://developers.openai.com/api/docs/pricing, read 2026-09-21. Cached input
# is the read rate. Cache *writes* are billed at 1.25x the uncached input rate on
# GPT-5.6 and later; see https://developers.openai.com/api/docs/guides/prompt-caching.
# Each input token is billed at exactly one of the three rates -- cache pricing is not
# an additive fee -- which is why cost_usd subtracts below.
PRICING_PER_MTOK: dict[str, tuple[float, float, float]] = {
    "gpt-6-astra": (10.00, 1.00, 50.00),
    "gpt-5.6-sol": (4.00, 0.40, 20.00),
    "gpt-5.6-terra": (2.00, 0.20, 12.00),
    "gpt-5.6-luna": (0.20, 0.02, 1.20),
    "gpt-5.5": (5.00, 0.50, 30.00),
    "gpt-5-mini": (0.25, 0.025, 2.00),
}

CACHE_WRITE_MULTIPLIER = 1.25


@dataclass
class Usage:
    """Token counts and derived cost for one or many calls.

    `cached_tokens` and `cache_write_tokens` are SUBSETS of `input_tokens`, following
    the OpenAI usage object. They are not added on top of it.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    calls: int = 0
    latencies_s: list[float] = field(default_factory=list)

    def add(self, other: Usage) -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cached_tokens += other.cached_tokens
        self.cache_write_tokens += other.cache_write_tokens
        self.reasoning_tokens += other.reasoning_tokens
        self.calls += other.calls
        self.latencies_s.extend(other.latencies_s)

    def cost_usd(self, model: str) -> float:
        if model not in PRICING_PER_MTOK:
            return float("nan")
        in_rate, cached_rate, out_rate = PRICING_PER_MTOK[model]
        uncached = max(0, self.input_tokens - self.cached_tokens - self.cache_write_tokens)
        return (
            uncached * in_rate
            + self.cache_write_tokens * in_rate * CACHE_WRITE_MULTIPLIER
            + self.cached_tokens * cached_rate
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
            "reasoning_tokens": self.reasoning_tokens,
            "cached_tokens": self.cached_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "total_cost_usd": round(total, 4),
            "cost_per_ticket_usd": round(total / self.calls, 6) if self.calls else None,
            "latency_mean_s": round(sum(lat) / n, 2) if n else None,
            "latency_p50_s": pct(0.50),
            "latency_p95_s": pct(0.95),
        }


def get_client() -> OpenAI:
    """Build a client, loading .env first. The key comes from the environment only."""
    load_dotenv(REPO_ROOT / ".env")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit(
            "OPENAI_API_KEY is not set.\n"
            "Put your key on the OPENAI_API_KEY= line in .env, or export the variable."
        )
    return OpenAI(max_retries=4)


def call_json(
    client: OpenAI,
    *,
    model: str,
    system: str,
    user: str,
    json_schema: dict,
    effort: str = "high",
    schema_name: str = "triage_result",
    max_output_tokens: int = 16000,
) -> tuple[dict, Usage]:
    """One request returning schema-valid JSON, plus its usage.

    `system` is identical across every ticket in a run and is sent as `instructions`, so
    it forms a stable prefix that prompt caching can reuse. Caching is automatic on
    OpenAI above a 1,024-token prefix -- there is no cache breakpoint to place.

    `max_output_tokens` is generous because reasoning tokens are drawn from the same
    budget as the answer; running out mid-reasoning yields a response with no message at
    all, which is raised rather than silently returned as a failure.
    """
    started = time.perf_counter()
    response = client.responses.create(
        model=model,
        instructions=system,
        input=user,
        reasoning={"effort": effort},
        text={
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": json_schema,
                "strict": True,
            }
        },
        max_output_tokens=max_output_tokens,
    )
    elapsed = time.perf_counter() - started

    text = _extract_text(response)

    details = getattr(response.usage, "input_tokens_details", None)
    output_details = getattr(response.usage, "output_tokens_details", None)
    usage = Usage(
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cached_tokens=getattr(details, "cached_tokens", 0) or 0,
        cache_write_tokens=getattr(details, "cache_write_tokens", 0) or 0,
        reasoning_tokens=getattr(output_details, "reasoning_tokens", 0) or 0,
        calls=1,
        latencies_s=[elapsed],
    )
    return json.loads(text), usage


def _extract_text(response) -> str:
    """Pull the JSON text out of a Response, distinguishing the ways it can go wrong.

    `response.output` interleaves reasoning items with the message, so it is walked
    rather than indexed. A safety refusal arrives as a `refusal` content block on an
    otherwise normal response, not as an exception.
    """
    for item in response.output:
        if getattr(item, "type", None) != "message":
            continue
        for block in item.content:
            if getattr(block, "type", None) == "refusal":
                raise RuntimeError(f"Request refused: {block.refusal}")
            text = getattr(block, "text", None)
            if text:
                return text

    status = getattr(response, "status", "unknown")
    reason = getattr(getattr(response, "incomplete_details", None), "reason", None)
    if reason == "max_output_tokens":
        raise RuntimeError(
            "Ran out of output tokens before producing an answer -- raise "
            "max_output_tokens or lower --effort."
        )
    raise RuntimeError(f"No message in response (status={status}, reason={reason})")
