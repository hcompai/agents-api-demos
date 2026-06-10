"""Tests for the typed-read tool ``get_product_prices``."""

from collections.abc import Callable
from decimal import Decimal

from fastmcp import Client
from pydantic import BaseModel

from examples.mcpify_anything.server import build_server
from tests.mcpify_anything._fakes import FakeRunner
from examples.mcpify_anything.tools.get_product_prices import Product, get_product_prices


def _answer(products: list[Product]) -> BaseModel:
    return get_product_prices.answer_model.model_validate({"items": [p.model_dump(mode="json") for p in products]})


async def test_get_product_prices_roundtrip(make_fake_runner: Callable[[BaseModel], FakeRunner]) -> None:
    runner = make_fake_runner(
        _answer([Product(name="Widget", price=Decimal("9.99"), currency="EUR", url="https://shop.test/w")])
    )
    mcp = build_server(runner)

    async with Client(mcp) as c:
        assert "get_product_prices" in {t.name for t in await c.list_tools()}
        result = await c.call_tool(
            "get_product_prices",
            {"args": {"site": "https://shop.test", "query": "widget", "max_results": 3}},
        )

    # The tool asks for the lean list; ``captured_at`` is added by the tool, not the agent.
    assert runner.last_spec is not None
    assert runner.last_spec.output_model is get_product_prices.answer_model
    assert result.data.captured_at is not None
    assert result.data.products[0].name == "Widget"
    assert result.data.products[0].currency == "EUR"


def test_answer_model_validates_items_object_losslessly() -> None:
    # The agent answers a JSON object ``{"items": [...]}`` (the schema we send it). The
    # auto-generated ``ProductList`` wrapper preserves every item.
    raw = {
        "items": [
            {"name": "Cable", "price": "6.99", "currency": "EUR", "url": "https://shop.test/c"},
            {"name": "Pad", "price": "3.50", "currency": "EUR", "url": "https://shop.test/p"},
        ],
    }
    parsed = get_product_prices.answer_model.model_validate(raw)
    assert [p.name for p in parsed.items] == ["Cable", "Pad"]
