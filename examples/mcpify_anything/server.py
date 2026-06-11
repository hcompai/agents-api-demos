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

    The DI seam tests target: pass a fake ``Runner`` and assert on the ``RunSpec`` each tool
    builds, no monkeypatching or network involved.
    """
    mcp: FastMCP = FastMCP("hai-agent-demos-mcpify-anything")
    register_specs(SPECS, mcp, runner)
    return mcp


def compose_server() -> FastMCP:
    """Production wiring: ``settings()`` → ``AsyncClient`` → ``CuaRunner`` → ``build_server``.

    Raises:
        RuntimeError: ``H_API_KEY`` is not set.
    """
    cfg = settings()
    runner = CuaRunner(AsyncClient(api_key=cfg.api_key, base_url=cfg.base_url), cfg.base_url, cfg.agent_artifact)
    return build_server(runner)


def main() -> None:
    """Entry point for the ``hai-agent-demos-mcpify-anything`` console script."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    compose_server().run()


if __name__ == "__main__":
    main()
