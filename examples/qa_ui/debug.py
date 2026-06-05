"""Local debug runner for the qa_ui tools — calls the MCP tool functions directly.

Bypasses the MCP transport so tracebacks and SDK logs land in your terminal.

    uv run debug-qa review --url https://example.com
    uv run debug-qa visual --url https://example.com --question "what color is the heading?"
"""

import json
import logging
import sys
import time

import tyro
from dotenv import load_dotenv

from examples.qa_ui.server import review_web_ui, visual_check


def review(url: str, instruction: str = "Review the page for usability and accessibility issues.") -> None:
    """Run ``review_web_ui`` and print the structured result."""
    started = time.monotonic()
    result = review_web_ui(url=url, instruction=instruction)
    print(f"completed in {time.monotonic() - started:.1f}s", file=sys.stderr)
    print(json.dumps(result.model_dump(), indent=2))


def visual(url: str, question: str) -> None:
    """Run ``visual_check`` and print the answer."""
    started = time.monotonic()
    answer = visual_check(url=url, question=question)
    print(f"completed in {time.monotonic() - started:.1f}s", file=sys.stderr)
    print(answer)


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
