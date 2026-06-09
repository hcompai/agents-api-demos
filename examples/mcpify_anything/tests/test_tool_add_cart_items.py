"""Tests for the action tool ``add_cart_items`` (action + read-back + client-derived totals)."""

from collections.abc import Callable
from decimal import Decimal

import pytest
from fastmcp import Client
from pydantic import BaseModel

from examples.mcpify_anything.server import build_server
from examples.mcpify_anything.tests._fakes import FakeRunner
from examples.mcpify_anything.tools.add_cart_items import CartLine, CartReceipt, add_cart_items


def _make_answer(lines: list[CartLine]) -> BaseModel:
    return add_cart_items.answer_model.model_validate({"items": [line.model_dump(mode="json") for line in lines]})


async def test_add_cart_items_adds_then_verifies(make_fake_runner: Callable[[BaseModel], FakeRunner]) -> None:
    # The agent authors only the pure list of cart lines; the tool derives the receipt.
    answer = _make_answer(
        [CartLine(name="Affirm Water Bottle", quantity=2, line_total=Decimal("14.00"), currency="USD")]
    )
    runner = make_fake_runner(answer)
    mcp = build_server(runner)

    async with Client(mcp) as c:
        result = await c.call_tool(
            "add_cart_items",
            {"args": {"items": [{"product_url": "https://shop.test/p/bottle", "quantity": 2}]}},
        )

    spec = runner.last_spec
    assert spec is not None
    assert spec.output_model is add_cart_items.answer_model
    assert "https://shop.test/p/bottle" in spec.task
    assert "quantity 2" in spec.task
    assert "cart" in spec.task.lower()
    # Receipt: status/total/currency/evidence derived client-side; requested items echoed.
    assert result.data.status == "added"
    assert result.data.requested_items[0].quantity == 2
    # Price round-trips over MCP as a JSON string; compare numerically.
    assert Decimal(str(result.data.cart_total)) == Decimal("14.00")
    assert result.data.currency == "USD"
    assert "Affirm Water Bottle" in result.data.evidence


async def test_add_cart_items_empty_cart_is_noop(make_fake_runner: Callable[[BaseModel], FakeRunner]) -> None:
    runner = make_fake_runner(_make_answer([]))
    mcp = build_server(runner)
    async with Client(mcp) as c:
        result = await c.call_tool(
            "add_cart_items",
            {"args": {"items": [{"product_url": "https://shop.test/p/bottle", "quantity": 1}]}},
        )
    assert result.data.status == "noop"
    assert result.data.cart_total is None


async def test_add_cart_items_rejects_empty_items(make_fake_runner: Callable[[BaseModel], FakeRunner]) -> None:
    mcp = build_server(make_fake_runner(_make_answer([])))
    async with Client(mcp) as c:
        with pytest.raises(Exception):
            await c.call_tool("add_cart_items", {"args": {"items": []}})


async def test_mixed_currency_lines_yield_none_total_and_currency(
    make_fake_runner: Callable[[BaseModel], FakeRunner],
) -> None:
    # A real cart with mixed-currency lines must NOT silently report a single currency or
    # a numerically-correct-but-meaningless sum. ``cart_total`` and ``currency`` both become
    # None; the lines themselves are still surfaced so the caller can see what the agent read.
    answer = _make_answer(
        [
            CartLine(name="Bottle", quantity=1, line_total=Decimal("9.00"), currency="USD"),
            CartLine(name="Notebook", quantity=1, line_total=Decimal("12.00"), currency="EUR"),
        ]
    )
    mcp = build_server(make_fake_runner(answer))
    async with Client(mcp) as c:
        result = await c.call_tool(
            "add_cart_items",
            {
                "args": {
                    "items": [
                        {"product_url": "https://shop.test/p/bottle", "quantity": 1},
                        {"product_url": "https://shop.test/p/notebook", "quantity": 1},
                    ]
                }
            },
        )

    assert result.data.status == "added"
    assert result.data.cart_total is None
    assert result.data.currency is None
    assert len(result.data.lines) == 2


def test_cart_total_is_safe_against_empty_lines() -> None:
    # Local invariant: ``_cart_total([])`` must not IndexError, regardless of whether the
    # caller already filtered via ``_currency``. Guards against future refactors of
    # ``_currency`` that might let an empty list reach ``_cart_total`` directly.
    assert CartReceipt._cart_total([]) is None


async def test_single_currency_sums_unchanged(make_fake_runner: Callable[[BaseModel], FakeRunner]) -> None:
    # Regression guard: the mixed-currency fix must NOT break single-currency aggregation.
    answer = _make_answer(
        [
            CartLine(name="Bottle", quantity=1, line_total=Decimal("9.00"), currency="USD"),
            CartLine(name="Mug", quantity=1, line_total=Decimal("4.50"), currency="USD"),
        ]
    )
    mcp = build_server(make_fake_runner(answer))
    async with Client(mcp) as c:
        result = await c.call_tool(
            "add_cart_items",
            {
                "args": {
                    "items": [
                        {"product_url": "https://shop.test/p/bottle", "quantity": 1},
                        {"product_url": "https://shop.test/p/mug", "quantity": 1},
                    ]
                }
            },
        )

    assert result.data.currency == "USD"
    assert Decimal(str(result.data.cart_total)) == Decimal("13.50")
