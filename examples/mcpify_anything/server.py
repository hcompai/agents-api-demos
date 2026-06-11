"""FastMCP server exposing a single typed-extraction tool over a cloud browser agent."""

from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from hai_agents import Agent, Client, run_session

from examples._shared import browser_env, require_api_key, setup_server_logging

_OPERATOR_INSTRUCTIONS = (Path(__file__).parent / "prompts" / "extractor_instructions.md").read_text()

mcp = FastMCP("hai-agent-demos-mcpify-anything")
_client_instance: Client | None = None


@mcp.tool
def extract(url: str, task: str, answer_schema: dict[str, Any]) -> dict[str, Any]:
    """Open a URL, follow a natural-language task, and return JSON matching ``answer_schema``.

    Args:
        url: Page the browser agent should start on.
        task: What the agent should do or read once on the page.
        answer_schema: JSON Schema describing the shape of the answer the agent must return.
    """
    result = run_session(
        _client(),
        agent=Agent(
            name="extractor",
            description="Reads structured data off a web page.",
            instructions=_OPERATOR_INSTRUCTIONS,
            environments=[browser_env(url)],
            answer_format=answer_schema,
        ),
        messages=task,
        max_steps=20,
        max_time_s=180.0,
    )
    if isinstance(result.answer, dict):
        return result.answer
    raise RuntimeError(f"extractor did not return a structured answer (status={result.status})")


def _client() -> Client:
    global _client_instance
    if _client_instance is None:
        _client_instance = Client(api_key=require_api_key())
    return _client_instance


def main() -> None:
    """Entry point for the ``hai-agent-demos-mcpify-anything`` console script."""
    setup_server_logging()
    mcp.run()


if __name__ == "__main__":
    main()
