"""FastMCP server exposing the mcpify-anything typed-toolkit example."""

import logging
import os

from fastmcp import FastMCP
from hai_agents import AsyncClient, HaiAgentsEnvironment

from examples.mcpify_anything.runner import CuaRunner
from examples.mcpify_anything.tool import register_specs
from examples.mcpify_anything.tools import SPECS

LOGGER = logging.getLogger("agent-sdk-demo-mcpify-anything")
_DEFAULT_BASE_URL = HaiAgentsEnvironment.EU.value
# Published agent build that matches the tool prompts (and bakes in the answer-format fix).
_DEFAULT_AGENT_ARTIFACT = "mcpify-anything-agent"


def build_server() -> FastMCP:
    """Compose a FastMCP server whose tools are wired to the lazy-built ``CuaRunner``.

    Returns:
        A ready-to-run FastMCP instance with every tool in ``SPECS`` registered.
    """
    mcp: FastMCP = FastMCP("agent-sdk-demo-mcpify-anything")
    register_specs(SPECS, mcp, _runner())
    return mcp


def main() -> None:
    """Entry point used by the ``agent-sdk-demo-mcpify-anything`` console script."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    build_server().run()


_runner_instance: CuaRunner | None = None


def _runner() -> CuaRunner:
    # Lazy singleton — keeps imports cheap and lets the FastMCP server boot even when the
    # API key isn't set (we fail loud on the first tool call, matching qa_mcp's pattern).
    global _runner_instance
    if _runner_instance is None:
        api_key = os.environ.get("H_API_KEY")
        if not api_key:
            raise RuntimeError(
                "H_API_KEY is not set. Copy .env.example to .env and add a key from "
                "https://portal.hcompany.ai, then re-run."
            )
        base_url = os.environ.get("H_BASE_URL", _DEFAULT_BASE_URL)
        artifact = os.environ.get("H_AGENT_ARTIFACT", _DEFAULT_AGENT_ARTIFACT)
        _runner_instance = CuaRunner(AsyncClient(api_key=api_key, base_url=base_url), base_url, artifact)
    return _runner_instance


if __name__ == "__main__":
    main()
