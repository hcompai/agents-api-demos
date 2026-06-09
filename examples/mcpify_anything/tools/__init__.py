"""Explicit registry of every ``ToolSpec`` exposed by this example."""

from examples.mcpify_anything.tool import ToolSpec
from examples.mcpify_anything.tools.add_cart_items import add_cart_items
from examples.mcpify_anything.tools.extract import extract
from examples.mcpify_anything.tools.get_product_prices import get_product_prices

# Adding a tool: drop a new module under ``tools/``, decorate with ``@browser_tool``, then
# import its spec here and append to ``SPECS``. This explicit list is intentional — the
# registrar's contents should be visible at a glance, not derived from a filesystem walk.
SPECS: tuple[ToolSpec, ...] = (extract, get_product_prices, add_cart_items)
