"""FastMCP server exposing the mcpify-anything typed-toolkit example."""

import logging

from fastmcp import FastMCP
from hai_agents import AsyncClient

from examples.mcpify_anything.config import settings
from examples.mcpify_anything.runner import CuaRunner, Runner
from examples.mcpify_anything.tool import register_specs
from examples.mcpify_anything.tools import SPECS


def build_server(runner: Runner) -> FastMCP:
    """Compose a FastMCP server whose tools are wired to the injected runner.

    This is the DI surface tests target: they pass a fake ``Runner`` to assert on the
    ``RunSpec`` each tool builds, without monkeypatching globals or hitting the network.

    Args:
        runner: The runner that backs every tool call.

    Returns:
        A ready-to-run FastMCP instance with every tool in ``SPECS`` registered.
    """
    mcp: FastMCP = FastMCP("agent-sdk-demo-mcpify-anything")
    register_specs(SPECS, mcp, runner)
    return mcp


def compose_server() -> FastMCP:
    """Production wiring: settings -> AsyncClient -> CuaRunner -> ``build_server``.

    Validates ``H_API_KEY`` at boot time (via ``settings()``) so a missing key fails
    before Claude Code can even register the tools, rather than surfacing mid-conversation.

    Returns:
        A ready-to-run FastMCP instance backed by a live ``CuaRunner``.

    Raises:
        RuntimeError: ``H_API_KEY`` is not set in the environment.
    """
    cfg = settings()
    runner = CuaRunner(AsyncClient(api_key=cfg.api_key, base_url=cfg.base_url), cfg.base_url, cfg.agent_artifact)
    return build_server(runner)


def main() -> None:
    """Entry point used by the ``agent-sdk-demo-mcpify-anything`` console script."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    compose_server().run()


if __name__ == "__main__":
    main()
