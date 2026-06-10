"""Shared type aliases used by multiple tools."""

from decimal import Decimal
from typing import Annotated

from pydantic import WithJsonSchema

# Pydantic's default Decimal JSON schema carries a regex ``pattern`` with a negative
# lookahead, which MCP clients that validate structured output with a Rust regex
# engine cannot compile. We keep exact Decimal validation but advertise a plain
# number-or-string schema so any host can consume the tool output.
Price = Annotated[Decimal, WithJsonSchema({"anyOf": [{"type": "number"}, {"type": "string"}]})]
