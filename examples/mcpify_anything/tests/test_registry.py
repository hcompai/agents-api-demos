"""Tests guarding the explicit ``SPECS`` registry against drift."""

from fastmcp import Client
from pydantic import BaseModel

from examples.mcpify_anything.runner import RunSpec
from examples.mcpify_anything.server import build_server
from examples.mcpify_anything.tool import ToolSpec
from examples.mcpify_anything.tools import SPECS

_EXPECTED_TOOLS = {"extract", "get_product_prices", "add_cart_items"}


class _NoopRunner:
    """Implements ``Runner`` for listing only; ``run()`` is never invoked when listing tools."""

    async def run(self, spec: RunSpec[BaseModel]) -> BaseModel:
        raise AssertionError("the registry guard lists tools; it must not execute them")


def test_specs_tuple_contains_every_shipped_tool() -> None:
    # Static guard: the explicit registry tuple itself names exactly the shipped tools.
    # If you add a tool module, append its spec to ``SPECS`` and update this assertion.
    assert {spec.name for spec in SPECS} == _EXPECTED_TOOLS
    assert all(isinstance(spec, ToolSpec) for spec in SPECS)


async def test_server_registers_every_spec() -> None:
    # End-to-end guard: ``build_server`` actually wires every entry in ``SPECS`` to FastMCP.
    # Bridges the static check above to the running server's surface.
    mcp = build_server(_NoopRunner())
    async with Client(mcp) as client:
        registered = {tool.name for tool in await client.list_tools()}
    assert registered == _EXPECTED_TOOLS
