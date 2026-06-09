"""Tests guarding the explicit ``SPECS`` registry against drift."""

from fastmcp import Client
from pydantic import BaseModel

from examples.mcpify_anything.runner import RunSpec
from examples.mcpify_anything.server import build_server
from examples.mcpify_anything.tools import SPECS


class _NoopRunner:
    """Implements ``Runner`` for listing only; ``run()`` is never invoked when listing tools."""

    async def run(self, spec: RunSpec[BaseModel]) -> BaseModel:
        raise AssertionError("the registry guard lists tools; it must not execute them")


async def test_server_registers_every_spec_in_tuple() -> None:
    # Single source of truth: ``SPECS`` itself names the shipped tools, and ``build_server``
    # must wire every entry into FastMCP. Adding a tool means appending to ``SPECS`` — this
    # test then follows automatically.
    mcp = build_server(_NoopRunner())
    async with Client(mcp) as client:
        registered = {tool.name for tool in await client.list_tools()}
    assert registered == {spec.name for spec in SPECS}
    assert registered, "SPECS must not be empty — at least one tool should ship"
