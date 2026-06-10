"""Tests for server wiring: the ``SPECS`` registry and the production ``compose_server`` path."""

import pytest
from fastmcp import Client, FastMCP
from pydantic import BaseModel

from examples.mcpify_anything.runner import RunSpec
from examples.mcpify_anything.server import build_server, compose_server
from examples.mcpify_anything.tools import SPECS


class _NoopRunner:
    """Implements ``Runner`` for listing only; ``run()`` is never invoked when listing tools."""

    async def run(self, spec: RunSpec[BaseModel]) -> BaseModel:
        raise AssertionError("the registry guard lists tools; it must not execute them")


async def test_server_registers_every_spec_in_tuple() -> None:
    # ``SPECS`` is the single source of truth: every entry must be wired into FastMCP.
    mcp = build_server(_NoopRunner())
    async with Client(mcp) as client:
        registered = {tool.name for tool in await client.list_tools()}
    assert registered == {spec.name for spec in SPECS}
    assert registered, "SPECS must not be empty — at least one tool should ship"


def test_compose_server_wires_real_collaborators(monkeypatch: pytest.MonkeyPatch) -> None:
    # The only test exercising the env -> AsyncClient -> CuaRunner chain; a kwarg or import
    # mismatch in ``compose_server()`` would TypeError here.
    monkeypatch.setenv("H_API_KEY", "hk-test")
    monkeypatch.delenv("H_BASE_URL", raising=False)
    monkeypatch.delenv("H_AGENT_ARTIFACT", raising=False)

    assert isinstance(compose_server(), FastMCP)


def test_compose_server_fails_loudly_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("H_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="H_API_KEY"):
        compose_server()
