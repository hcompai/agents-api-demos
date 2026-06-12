"""Standalone CLI for the extract_anything extractor, demoed on Wikipedia's Picture of the Day.

Same SDK call as ``examples/extract_anything/server.py``, exposed as a shell command. The
``picture`` subcommand is a vision-only showcase: Wikipedia's daily featured picture is just
a PNG/JPEG embedded in the page — the *visual* content lives in pixels, not the DOM. The
caption gives a hint, but the actual image description has to come from looking at the image.

    uv run extract-cli picture
"""

import sys
import time

import tyro
from dotenv import load_dotenv
from hai_agents import Agent, Client
from pydantic import BaseModel

from examples._shared import (
    browser_env,
    print_structured_answer,
    require_api_key,
    run_session_streaming,
    setup_cli_logging,
)
from examples.extract_anything.prompts import OPERATOR_INSTRUCTIONS


class FeaturedPicture(BaseModel):
    """Structured answer for the ``picture`` subcommand."""

    title: str  # Wikipedia's title for the picture
    image_description: str  # the agent's own visual description of what is in the image
    visible_text_in_image: str  # any text that appears inside the image itself (often empty)
    credit: str  # photographer / source attribution as shown on the page


def picture() -> None:
    """Describe Wikipedia's Picture of the Day by actually looking at the image."""
    started = time.monotonic()
    task = (
        "Open the Wikipedia main page and find the 'Picture of the day' section. "
        "Look at the image itself and describe what is visible in your own words — subject, "
        "setting, notable details, dominant colours. Transcribe any text rendered inside the "
        "image (leave empty if none). Read the title and the credit/attribution off the page. "
        "Return JSON matching the schema."
    )
    print("opening Wikipedia main page…", file=sys.stderr)
    result = run_session_streaming(
        _client(),
        started=started,
        agent=Agent(
            name="picture-describer",
            description="Describes Wikipedia's Picture of the Day by reading the image.",
            instructions=OPERATOR_INSTRUCTIONS,
            environments=[browser_env("https://en.wikipedia.org/wiki/Main_Page")],
            answer_format=FeaturedPicture.model_json_schema(),
        ),
        messages=task,
        max_steps=20,
        max_time_s=240.0,
    )
    print_structured_answer(result, FeaturedPicture, started)


def _client() -> Client:
    return Client(api_key=require_api_key())


def main() -> None:
    """Entry point for the ``extract-cli`` console script."""
    load_dotenv()
    setup_cli_logging()
    try:
        tyro.extras.subcommand_cli_from_dict({"picture": picture})
    except RuntimeError as exc:
        sys.exit(f"error: {exc}")


if __name__ == "__main__":
    main()
