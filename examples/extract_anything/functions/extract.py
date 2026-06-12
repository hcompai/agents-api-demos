"""Generic extraction tool — caller supplies the JSON Schema at call time.

All three surfaces (Python function, ``@mcp.tool``, CLI subcommand) live here. Unlike
the curated ``get_*`` tools this one returns a free-form ``dict`` because the schema is
caller-supplied — there's no static Pydantic model to validate into.
"""

import json
from typing import Annotated, Any

from hai_agents import Agent, Client, run_session
from pydantic import Field, HttpUrl

from examples._shared import browser_env
from examples.extract_anything.functions._common import (
    OPERATOR_PREAMBLE,
    get_client,
    mcp,
    run_dict_cli,
    url,
)


def extract(
    client: Client,
    *,
    site: HttpUrl,
    task: str,
    answer_schema: dict[str, Any],
) -> dict[str, Any]:
    """Open a site, follow a natural-language task, return JSON matching ``answer_schema``.

    The escape hatch for sites/shapes that don't have a dedicated curated tool.
    """
    result = run_session(
        client,
        agent=Agent(
            name="extractor",
            description="Reads structured data off a web page.",
            instructions=f"You browse websites and follow the caller's natural-language task.\n\n{OPERATOR_PREAMBLE}",
            environments=[browser_env(str(site))],
            answer_format=answer_schema,
        ),
        messages=task,
        max_steps=20,
        max_time_s=180.0,
    )
    if isinstance(result.answer, dict):
        return result.answer
    raise RuntimeError(f"extractor did not return a structured answer (status={result.status})")


@mcp.tool(name="extract")
def _mcp(
    site: HttpUrl,
    task: Annotated[str, Field(min_length=1, description="natural-language instruction for the agent")],
    answer_schema: Annotated[dict[str, Any], Field(description="JSON Schema describing the desired return shape")],
) -> dict[str, Any]:
    """Open a site, follow a natural-language task, return JSON matching ``answer_schema``."""
    return extract(get_client(), site=site, task=task, answer_schema=answer_schema)


def _cli(site: str, task: str, answer_schema: str) -> None:
    """Generic extract — ``answer_schema`` is a JSON string, e.g. ``'{"type":"object",...}'``."""
    schema = json.loads(answer_schema)
    run_dict_cli(
        "extract",
        budget_s=180.0,
        fn=lambda: extract(get_client(), site=url(site), task=task, answer_schema=schema),
    )


CLI_NAME = "extract"
CLI_FN = _cli
