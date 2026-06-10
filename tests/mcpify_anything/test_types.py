"""Tests for the shared ``Price`` type alias."""

from pydantic import BaseModel

from examples.mcpify_anything.types import Price


class _Has(BaseModel):
    p: Price


def test_price_schema_has_no_regex_pattern() -> None:
    # Rust-regex MCP clients can't compile pydantic's default Decimal pattern (negative
    # lookahead). Lock the override in so a pydantic upgrade reintroducing it fails here.
    assert "pattern" not in str(_Has.model_json_schema())


def test_price_schema_advertises_number_or_string() -> None:
    schema = _Has.model_json_schema()
    price_node = schema["properties"]["p"]
    assert price_node.get("anyOf") == [{"type": "number"}, {"type": "string"}]
