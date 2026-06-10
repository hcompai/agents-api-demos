"""Tests for the shared ``Price`` type alias — guards the rust-regex MCP-client workaround."""

from pydantic import BaseModel

from examples.mcpify_anything.types import Price


class _Has(BaseModel):
    p: Price


def test_price_schema_has_no_regex_pattern() -> None:
    # Rust-regex MCP clients can't compile pydantic's default Decimal pattern with its
    # negative lookahead. ``types.Price`` exists to strip that pattern; lock it in so a
    # future pydantic upgrade or refactor that reintroduces the pattern fails loudly here.
    assert "pattern" not in str(_Has.model_json_schema())


def test_price_schema_advertises_number_or_string() -> None:
    # The replacement schema must remain a number-or-string union; both forms are valid JSON
    # answers from the agent and both must validate against Decimal.
    schema = _Has.model_json_schema()
    price_node = schema["properties"]["p"]
    assert price_node.get("anyOf") == [{"type": "number"}, {"type": "string"}]
