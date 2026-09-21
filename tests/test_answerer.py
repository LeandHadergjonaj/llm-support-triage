"""No API key needed: the deterministic grounding logic, not the LLM call itself."""

from __future__ import annotations

from triage.answerer import (
    extract_order_ids,
    load_knowledge_base,
    load_orders,
    order_facts_block,
    system_prompt,
)


def test_extract_order_ids_finds_numbers_and_dedupes():
    assert extract_order_ids("cancel order 51986 please") == ["51986"]
    assert extract_order_ids("order #46399 and again order 46399") == ["46399"]
    assert extract_order_ids("no order mentioned here") == []


def test_order_facts_block_reports_a_real_order_verbatim():
    orders = load_orders()
    assert "51986" in orders
    block = order_facts_block("please cancel order 51986")
    assert "51986" in block
    assert orders["51986"]["dispatch_state"] in block


def test_order_facts_block_is_honest_about_a_missing_order():
    block = order_facts_block("what's happening with order 53004?")
    assert "no matching order record" in block.lower()
    assert "53004" in block


def test_order_facts_block_with_no_order_number_says_so():
    block = order_facts_block("do you accept Amex?")
    assert "no order number" in block.lower()


def test_knowledge_base_loads_all_six_docs_not_the_readme():
    kb = load_knowledge_base()
    assert "readme" not in kb.lower().split("###")[0].lower()
    for name in (
        "returns_and_refunds", "delivery_and_shipping", "cancellations_and_order_changes",
        "payments_and_billing", "accounts", "product_safety",
    ):
        assert name in kb


def test_self_and_human_prompts_differ_on_role():
    self_prompt = system_prompt("self")
    human_prompt = system_prompt("human", "product_safety")
    assert "reply to the customer directly" in self_prompt.lower()
    assert "escalated to a person" in human_prompt.lower()
    assert "product_safety" in human_prompt
    assert self_prompt != human_prompt


def test_human_prompt_falls_back_when_no_formal_reason():
    human_prompt = system_prompt("human", "")
    assert "low routing confidence" in human_prompt.lower()
