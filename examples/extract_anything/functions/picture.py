"""Describe Wikipedia's *Picture of the Day* by actually looking at the image.

All three surfaces for this tool live here: the typed Python function, the ``@mcp.tool``
wrapper, and the CLI subcommand (the streaming one — picture is the showcase demo, so
the CLI uses ``run_session_streaming`` for a live event tail).
"""

import sys
import time

from hai_agents import Agent, Client
from pydantic import BaseModel, Field

from examples._shared import browser_env, print_structured_answer, run_session_streaming
from examples.extract_anything.functions._common import get_client, mcp, run_extraction
from examples.extract_anything.prompts import OPERATOR_INSTRUCTIONS


class FeaturedPicture(BaseModel):
    """Structured answer for the picture-of-the-day function."""

    title: str = Field(description="Wikipedia's title for the picture")
    image_description: str = Field(description="agent's own visual description of what is in the image")
    visible_text_in_image: str = Field(description="any text rendered inside the image itself (empty if none)")
    credit: str = Field(description="photographer / source attribution as shown on the page")


_TASK = (
    "Open the Wikipedia main page and find the 'Picture of the day' section. "
    "Look at the image itself and describe what is visible in your own words — subject, "
    "setting, notable details, dominant colours. Transcribe any text rendered inside the "
    "image (leave empty if none). Read the title and the credit/attribution off the page."
)


def describe_picture_of_the_day(client: Client) -> FeaturedPicture:
    """Describe today's Wikipedia *Picture of the Day* by looking at the image.

    Vision-only showcase: the caption gives a hint, but the actual description has to
    come from looking at the embedded raster image.
    """
    return run_extraction(
        client,
        name="picture-describer",
        description="Describes Wikipedia's Picture of the Day by reading the image.",
        persona="You describe images by looking at them.",
        start_url="https://en.wikipedia.org/wiki/Main_Page",
        task=_TASK,
        answer_model=FeaturedPicture,
        max_steps=20,
        max_time_s=240.0,
    )


@mcp.tool(name="describe_picture_of_the_day")
def _mcp() -> FeaturedPicture:
    """Describe today's Wikipedia *Picture of the Day* by looking at the image."""
    return describe_picture_of_the_day(get_client())


def _cli() -> None:
    """Describe Wikipedia's Picture of the Day by actually looking at the image.

    Uses the streaming runner so the user sees a live event tail — the picture demo is
    the one we want to watch interactively.
    """
    started = time.monotonic()
    print("opening Wikipedia main page…", file=sys.stderr)
    result = run_session_streaming(
        get_client(),
        started=started,
        agent=Agent(
            name="picture-describer",
            description="Describes Wikipedia's Picture of the Day by reading the image.",
            instructions=f"You describe images by looking at them.\n\n{OPERATOR_INSTRUCTIONS}",
            environments=[browser_env("https://en.wikipedia.org/wiki/Main_Page")],
            answer_format=FeaturedPicture.model_json_schema(),
        ),
        messages=_TASK,
        max_steps=20,
        max_time_s=240.0,
    )
    print_structured_answer(result, FeaturedPicture, started)


CLI_NAME = "picture"
CLI_FN = _cli
