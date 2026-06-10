"""FastMCP server exposing QA tools backed by the hai-agents SDK."""

import json
import logging

from fastmcp import FastMCP
from hai_agents import Client, run_session

from examples._shared import (
    REVIEWER_INSTRUCTIONS,
    ReviewResult,
    browser_env,
    load_agent_skills,
    require_api_key,
)

LOGGER = logging.getLogger("agent-sdk-demo-qa")
mcp = FastMCP("agent-sdk-demo-qa")


@mcp.tool
def review_web_ui(url: str, instruction: str) -> ReviewResult:
    """Review a remote web UI and return structured QA findings."""
    result = run_session(
        _client(),
        agent={
            "name": "ui-reviewer",
            "description": "Reviews a web UI for usability, accessibility, and obvious bugs.",
            "instructions": REVIEWER_INSTRUCTIONS,
            "skills": load_agent_skills(),
            "environments": [browser_env(url)],
        },
        messages=instruction,
        max_steps=25,
        max_time_s=360.0,
        answer_format=ReviewResult.model_json_schema(),
    )
    if isinstance(result.answer, dict):
        return ReviewResult.model_validate(result.answer)
    raise RuntimeError(f"ui-reviewer did not return a structured answer (status={result.status})")


@mcp.tool
def visual_check(url: str, question: str) -> str:
    """Open a URL and answer a single visual question about the page."""
    result = run_session(
        _client(),
        agent={
            "name": "visual-checker",
            "description": "Answers a single visual question about a web page.",
            "instructions": "Open the page and answer the user's question in one or two sentences.",
            "environments": [browser_env(url)],
        },
        messages=question,
        max_steps=3,
        max_time_s=120.0,
    )
    answer = result.answer
    if answer is None:
        return f"(no answer; status={result.status})"
    return answer if isinstance(answer, str) else json.dumps(answer)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    mcp.run()


_client_instance: Client | None = None


def _client() -> Client:
    global _client_instance
    if _client_instance is None:
        _client_instance = Client(api_key=require_api_key())
    return _client_instance


if __name__ == "__main__":
    main()
