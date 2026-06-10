"""Explicit registry of every ``ToolSpec`` exposed by this example."""

from examples.mcpify_anything.tool import ToolSpec
from examples.mcpify_anything.tools.add_cart_items import add_cart_items
from examples.mcpify_anything.tools.extract import extract
from examples.mcpify_anything.tools.get_product_prices import get_product_prices

# Add a tool: drop a new module under ``tools/``, decorate it with ``@browser_tool``, then
# import and append it here. Explicit by design — the registry should be readable at a glance.
SPECS: tuple[ToolSpec, ...] = (extract, get_product_prices, add_cart_items)
