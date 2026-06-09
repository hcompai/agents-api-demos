"""Tests for the production wiring path in ``server.compose_server``."""

import pytest
from fastmcp import FastMCP

from examples.mcpify_anything.server import compose_server


def test_compose_server_wires_real_collaborators(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression guard for production wiring drift: any kwarg/import mismatch in the
    # AsyncClient or CuaRunner construction inside ``compose_server()`` would TypeError here.
    # The rest of the suite injects fake runners via ``build_server``, bypassing this path —
    # so this test is the only one that catches breakage in the env -> SDK -> runner chain.
    monkeypatch.setenv("H_API_KEY", "hk-test")
    monkeypatch.delenv("H_BASE_URL", raising=False)
    monkeypatch.delenv("H_AGENT_ARTIFACT", raising=False)

    mcp = compose_server()

    assert isinstance(mcp, FastMCP)


def test_compose_server_fails_loudly_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("H_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="H_API_KEY"):
        compose_server()
