"""Local debug runner — calls run_session directly so the full event stream is available.

Bypasses the MCP transport so tracebacks and SDK logs land in your terminal.
Every run auto-saves a trace to traces/<subcommand>_<timestamp>.json for post-run inspection.

    uv run debug-qa review --url https://example.com
    uv run debug-qa visual --url https://example.com --question "what color is the heading?"
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import tyro
from dotenv import load_dotenv
from hai_agents import Client, SessionRunResult, run_session

from examples._shared import (
    print_freeform_answer,
    print_structured_answer,
    require_api_key,
    setup_cli_logging,
)
from examples.qa.shared import ReviewResult, build_reviewer_agent, build_visual_checker_agent

TRACES_DIR = Path("traces")


def review(url: str, instruction: str = "Review the page for usability and accessibility issues.") -> None:
    """Run a UI review, print the structured result, and save a full trace to traces/.

    Args:
        url: Page the reviewer should open.
        instruction: Natural-language brief telling the reviewer what to focus on.
    """
    started = time.monotonic()
    result = run_session(
        _client(),
        agent=build_reviewer_agent(url),
        messages=instruction,
        max_steps=25,
        max_time_s=360.0,
    )
    trace_path = _save_trace("review", url, instruction, time.monotonic() - started, result)
    print(f"trace → {trace_path}", file=sys.stderr)
    print_structured_answer(result, ReviewResult, started)


def visual(url: str, question: str) -> None:
    """Run a visual question, print the answer, and save a full trace to traces/.

    Args:
        url: Page the agent should open.
        question: One short question about what is visible on the page.
    """
    started = time.monotonic()
    result = run_session(
        _client(),
        agent=build_visual_checker_agent(url),
        messages=question,
        max_steps=3,
        max_time_s=120.0,
    )
    trace_path = _save_trace("visual", url, question, time.monotonic() - started, result)
    print(f"trace → {trace_path}", file=sys.stderr)
    print_freeform_answer(result, started)


def _client() -> Client:
    return Client(api_key=require_api_key())


def _save_trace(subcommand: str, url: str, instruction: str, elapsed: float, result: SessionRunResult) -> Path:
    TRACES_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = TRACES_DIR / f"{subcommand}_{timestamp}.json"
    events = []
    for event in result.events:
        try:
            events.append({"type": event.type, "data": event.data})
        except Exception:
            events.append({"type": type(event).__name__, "data": repr(event)})
    path.write_text(
        json.dumps(
            {
                "url": url,
                "instruction": instruction,
                "elapsed_s": round(elapsed, 2),
                "status": result.status,
                "answer": result.answer,
                "events": events,
            },
            indent=2,
        )
    )
    return path


def main() -> None:
    """Entry point for the ``debug-qa`` console script."""
    load_dotenv()
    setup_cli_logging(level=logging.DEBUG, http_level=logging.INFO)
    try:
        tyro.extras.subcommand_cli_from_dict({"review": review, "visual": visual})
    except RuntimeError as exc:
        sys.exit(f"error: {exc}")


if __name__ == "__main__":
    main()
