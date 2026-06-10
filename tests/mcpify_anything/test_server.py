"""Server wiring tests: ``SPECS`` registry coverage and ``compose_server`` boot."""

import pytest
from fastmcp import Client, FastMCP
from pydantic import BaseModel

from examples.mcpify_anything.runner import RunSpec
from examples.mcpify_anything.server import build_server, compose_server
from examples.mcpify_anything.tools import SPECS


class _NoopRunner:
    async def run(self, spec: RunSpec[BaseModel]) -> BaseModel:
        raise AssertionError("the registry guard lists tools; it must not execute them")


async def test_server_registers_every_spec_in_tuple() -> None:
    mcp = build_server(_NoopRunner())
    async with Client(mcp) as client:
        registered = {tool.name for tool in await client.list_tools()}
    assert registered == {spec.name for spec in SPECS}
    assert registered, "SPECS must not be empty"


def test_compose_server_wires_real_collaborators(monkeypatch: pytest.MonkeyPatch) -> None:
    # Smoke test for the env → AsyncClient → CuaRunner chain.
    monkeypatch.setenv("H_API_KEY", "hk-test")
    monkeypatch.delenv("H_BASE_URL", raising=False)
    monkeypatch.delenv("H_AGENT_ARTIFACT", raising=False)

    assert isinstance(compose_server(), FastMCP)


def test_compose_server_fails_loudly_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("H_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="H_API_KEY"):
        compose_server()
