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
from hai_agents import Client, run_session

from examples._shared import (
    REVIEWER_INSTRUCTIONS,
    ReviewResult,
    browser_env,
    load_agent_skills,
    require_api_key,
)

TRACES_DIR = Path("traces")


def review(url: str, instruction: str = "Review the page for usability and accessibility issues.") -> None:
    """Run a UI review, print the structured result, and save a full trace to traces/."""
    started = time.monotonic()
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
    elapsed = time.monotonic() - started
    print(f"completed in {elapsed:.1f}s (status={result.status})", file=sys.stderr)

    trace_path = _save_trace("review", url, instruction, elapsed, result)
    print(f"trace → {trace_path}", file=sys.stderr)

    if not isinstance(result.answer, dict):
        sys.exit(f"error: agent did not return a structured answer (status={result.status})")
    print(json.dumps(ReviewResult.model_validate(result.answer).model_dump(), indent=2))


def visual(url: str, question: str) -> None:
    """Run a visual question, print the answer, and save a full trace to traces/."""
    started = time.monotonic()
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
    elapsed = time.monotonic() - started
    print(f"completed in {elapsed:.1f}s (status={result.status})", file=sys.stderr)

    trace_path = _save_trace("visual", url, question, elapsed, result)
    print(f"trace → {trace_path}", file=sys.stderr)

    answer = result.answer
    if answer is None:
        sys.exit(f"error: no answer (status={result.status})")
    print(answer if isinstance(answer, str) else json.dumps(answer))


def _save_trace(subcommand: str, url: str, instruction: str, elapsed: float, result) -> Path:
    TRACES_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = TRACES_DIR / f"{subcommand}_{timestamp}.json"

    events = []
    for e in result.events:
        try:
            events.append({"type": e.type, "data": e.data})
        except Exception:
            events.append({"type": type(e).__name__, "data": repr(e)})

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


def _client() -> Client:
    return Client(api_key=require_api_key())


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.DEBUG,
        stream=sys.stderr,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    logging.getLogger("httpcore").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.INFO)
    try:
        tyro.extras.subcommand_cli_from_dict({"review": review, "visual": visual})
    except RuntimeError as exc:
        sys.exit(f"error: {exc}")


if __name__ == "__main__":
    main()
