"""Deterministic typed functions over the browser agent.

Each helper here pins a prompt + schema + agent config for one task. Surfaces (CLI, MCP
server) import these and pick their runner — ``run_session`` for one-shots,
``run_session_streaming`` if they want a live event tail. The function itself is what the
caller sees; the agent is an implementation detail.
"""

from pathlib import Path
from typing import Any

from hai_agents import Agent, Client, run_session
from pydantic import BaseModel

from examples._shared import browser_env

_OPERATOR_INSTRUCTIONS = (Path(__file__).parent / "prompts" / "extractor_instructions.md").read_text()


class FeaturedPicture(BaseModel):
    """Structured answer for the picture-of-the-day deterministic function."""

    title: str  # Wikipedia's title for the picture
    image_description: str  # the agent's own visual description of what is in the image
    visible_text_in_image: str  # any text that appears inside the image itself (often empty)
    credit: str  # photographer / source attribution as shown on the page


PICTURE_TASK = (
    "Open the Wikipedia main page and find the 'Picture of the day' section. "
    "Look at the image itself and describe what is visible in your own words — subject, "
    "setting, notable details, dominant colours. Transcribe any text rendered inside the "
    "image (leave empty if none). Read the title and the credit/attribution off the page. "
    "Return JSON matching the schema."
)

PICTURE_MAX_STEPS = 20
PICTURE_MAX_TIME_S = 240.0


def picture_agent() -> Agent:
    """Configured browser agent for the picture-of-the-day function."""
    return Agent(
        name="picture-describer",
        description="Describes Wikipedia's Picture of the Day by reading the image.",
        instructions=_OPERATOR_INSTRUCTIONS,
        environments=[browser_env("https://en.wikipedia.org/wiki/Main_Page")],
        answer_format=FeaturedPicture.model_json_schema(),
    )


def describe_picture_of_the_day(client: Client) -> dict[str, Any]:
    """Describe today's Wikipedia *Picture of the Day* by looking at the image.

    Deterministic function: fixed prompt, fixed schema, zero caller args beyond the SDK
    client. Use it from Python directly, or expose it as an MCP tool — ``server.py`` does
    the latter; both call paths land here.
    """
    result = run_session(
        client,
        agent=picture_agent(),
        messages=PICTURE_TASK,
        max_steps=PICTURE_MAX_STEPS,
        max_time_s=PICTURE_MAX_TIME_S,
    )
    if isinstance(result.answer, dict):
        return result.answer
    raise RuntimeError(f"picture-describer did not return a structured answer (status={result.status})")
