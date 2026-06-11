"""Standalone CLI for the hai-agents-powered QA reviewer.

Same SDK calls as ``examples/qa/mcp/server.py``, exposed as a plain shell command instead of an MCP
server. Designed to be invoked from a terminal or from the ``hai-qa-via-cli`` Claude Code skill (see
``skills/hai-qa-via-cli/SKILL.md``).

    uv run qa-cli review --url https://example.com --instruction "look for broken links"
    uv run qa-cli visual --url https://example.com --question "what color is the heading?"
"""

import sys
import time

import tyro
from dotenv import load_dotenv
from hai_agents import Agent, Client, run_session

from examples._shared import (
    browser_env,
    print_freeform_answer,
    print_structured_answer,
    require_api_key,
    setup_cli_logging,
)
from examples.qa.shared import REVIEWER_INSTRUCTIONS, ReviewResult, load_agent_skills

VISUAL_INSTRUCTIONS = "Open the page and answer the user's question in one or two sentences."


def review(url: str, instruction: str = "Do a general usability and accessibility review.") -> None:
    """Run a UI review and print the structured ``ReviewResult`` as JSON to stdout.

    Args:
        url: Page the reviewer should open.
        instruction: Natural-language brief telling the reviewer what to focus on.
    """
    started = time.monotonic()
    result = run_session(
        _client(),
        agent=Agent(
            name="ui-reviewer",
            description="Reviews a web UI for usability, accessibility, and obvious bugs.",
            instructions=REVIEWER_INSTRUCTIONS,
            skills=load_agent_skills(),
            environments=[browser_env(url)],
            answer_format=ReviewResult.model_json_schema(),
        ),
        messages=instruction,
        max_steps=25,
        max_time_s=360.0,
    )
    print_structured_answer(result, ReviewResult, started)


def visual(url: str, question: str) -> None:
    """Open a URL and answer a single visual question; print the answer to stdout.

    Args:
        url: Page the agent should open.
        question: One short question about what is visible on the page.
    """
    started = time.monotonic()
    result = run_session(
        _client(),
        agent=Agent(
            name="visual-checker",
            description="Answers a single visual question about a web page.",
            instructions=VISUAL_INSTRUCTIONS,
            environments=[browser_env(url)],
        ),
        messages=question,
        max_steps=3,
        max_time_s=120.0,
    )
    print_freeform_answer(result, started)


def _client() -> Client:
    return Client(api_key=require_api_key())


def main() -> None:
    """Entry point for the ``qa-cli`` console script."""
    load_dotenv()
    setup_cli_logging()
    try:
        tyro.extras.subcommand_cli_from_dict({"review": review, "visual": visual})
    except RuntimeError as exc:
        sys.exit(f"error: {exc}")


if __name__ == "__main__":
    main()
