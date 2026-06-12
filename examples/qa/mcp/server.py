"""FastMCP server exposing QA tools backed by the hai-agents SDK."""

import json

from dotenv import load_dotenv
from fastmcp import FastMCP
from hai_agents import Client, run_session

from examples._shared import require_api_key, setup_server_logging
from examples.qa.shared import ReviewResult, build_reviewer_agent, build_visual_checker_agent

mcp = FastMCP("hai-agent-demos-qa")
_client_instance: Client | None = None


@mcp.tool
def review_web_ui(url: str, instruction: str) -> ReviewResult:
    """Review a remote web UI and return structured QA findings.

    Args:
        url: Page the reviewer agent should open and inspect.
        instruction: Natural-language brief telling the agent what to look for.
    """
    result = run_session(
        _client(),
        agent=build_reviewer_agent(url),
        messages=instruction,
        max_steps=25,
        max_time_s=360.0,
    )
    if isinstance(result.answer, dict):
        return ReviewResult.model_validate(result.answer)
    raise RuntimeError(f"ui-reviewer did not return a structured answer (status={result.status})")


@mcp.tool
def visual_check(url: str, question: str) -> str:
    """Open a URL and answer a single visual question about the page.

    Args:
        url: Page the agent should open.
        question: One short question about what is visible on the page.
    """
    result = run_session(
        _client(),
        agent=build_visual_checker_agent(url),
        messages=question,
        max_steps=3,
        max_time_s=120.0,
    )
    answer = result.answer
    if answer is None:
        return f"(no answer; status={result.status})"
    return answer if isinstance(answer, str) else json.dumps(answer)


def _client() -> Client:
    global _client_instance
    if _client_instance is None:
        _client_instance = Client(api_key=require_api_key())
    return _client_instance


def main() -> None:
    """Entry point for the ``hai-agent-demos-qa`` console script."""
    load_dotenv()
    setup_server_logging()
    mcp.run()


if __name__ == "__main__":
    main()
