"""Shared type aliases used by multiple tools."""

from decimal import Decimal
from typing import Annotated

from pydantic import WithJsonSchema

# Pydantic's default Decimal JSON schema carries a regex ``pattern`` with a negative lookahead
# that Rust-regex-backed MCP clients can't compile. Override the schema (validation still
# uses Decimal) so any host can consume the tool output.
Price = Annotated[Decimal, WithJsonSchema({"anyOf": [{"type": "number"}, {"type": "string"}]})]
