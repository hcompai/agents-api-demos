"""Explicit registry of every ``ToolSpec`` exposed by this example."""

from typing import Any

from examples.mcpify_anything.tool import ToolSpec
from examples.mcpify_anything.tools.add_cart_items import add_cart_items
from examples.mcpify_anything.tools.extract import extract
from examples.mcpify_anything.tools.get_product_prices import get_product_prices

# Adding a tool: drop a new module under ``tools/``, decorate with ``@browser_tool``, then
# import its spec here and append to ``SPECS``. This explicit list is intentional — the
# registrar's contents should be visible at a glance, not derived from a filesystem walk.
#
# ``ToolSpec[Any, Any, Any]`` because the tuple is heterogeneous — each spec has its own
# ``InputT/AnswerT/OutputT`` triple, which a single TypeVar can't express.
SPECS: tuple[ToolSpec[Any, Any, Any], ...] = (extract, get_product_prices, add_cart_items)
