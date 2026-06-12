"""Shared plumbing for the deterministic extract_anything functions.

This module owns the framework-level state — the FastMCP instance, the lazy SDK client,
the operator preamble, the cross-host-safe ``Price`` type, an answer-parser, and the
runner / CLI helpers. Each ``functions/<name>.py`` module imports what it needs from
here, so the three surfaces (Python function, ``@mcp.tool``, CLI subcommand) for one
tool all live in the same file as the function itself.

``server.py`` and ``cli.py`` end up as ~15-line orchestrators.
"""

import json
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Callable, TypeVar

from fastmcp import FastMCP
from hai_agents import Agent, Client, SessionRunResult, run_session
from pydantic import BaseModel, HttpUrl, TypeAdapter, WithJsonSchema

from examples._shared import browser_env, progress_spinner, require_api_key

# Loaded once at import; appended to each tool's persona instructions. Holds the
# universal "report what's shown, don't invent, no markdown" rule so per-tool strings
# stay focused on persona.
OPERATOR_PREAMBLE = (Path(__file__).parent.parent / "prompts" / "extractor_instructions.md").read_text()

# Pydantic's default JSON schema for ``Decimal`` includes a regex pattern with a negative
# lookahead that MCP clients backed by a Rust regex engine cannot compile. We keep exact
# Decimal validation but advertise a plain number-or-string schema so any host can consume
# the tool output.
Price = Annotated[Decimal, WithJsonSchema({"anyOf": [{"type": "number"}, {"type": "string"}]})]

# The single FastMCP instance every tool module decorates against. Importing a tool
# module registers its ``@mcp.tool`` as a side effect, so server.py just imports the
# functions package and then calls ``mcp.run()``.
mcp = FastMCP("hai-agent-demos-extract-anything")

T = TypeVar("T", bound=BaseModel)

_URL_ADAPTER: TypeAdapter[HttpUrl] = TypeAdapter(HttpUrl)
_client_instance: Client | None = None


def get_client() -> Client:
    """Return a cached SDK client, building it lazily from ``H_API_KEY`` on first use."""
    global _client_instance
    if _client_instance is None:
        _client_instance = Client(api_key=require_api_key())
    return _client_instance


def url(s: str) -> HttpUrl:
    """Validate a raw string into ``HttpUrl`` — used at the CLI edge where tyro hands us ``str``."""
    return _URL_ADAPTER.validate_python(s)


def parse_answer(result: SessionRunResult, model: type[T]) -> T:
    """Validate the agent's answer into ``model`` or raise with the session status."""
    if isinstance(result.answer, dict):
        return model.model_validate(result.answer)
    raise RuntimeError(f"agent did not return a structured answer (status={result.status})")


def run_extraction(
    client: Client,
    *,
    name: str,
    description: str,
    persona: str,
    start_url: str,
    task: str,
    answer_model: type[T],
    max_steps: int = 20,
    max_time_s: float = 180.0,
) -> T:
    """Build an agent, run a session, validate the answer into ``answer_model``."""
    result = run_session(
        client,
        agent=Agent(
            name=name,
            description=description,
            instructions=f"{persona}\n\n{OPERATOR_PREAMBLE}",
            environments=[browser_env(start_url)],
            answer_format=answer_model.model_json_schema(),
        ),
        messages=task,
        max_steps=max_steps,
        max_time_s=max_time_s,
    )
    return parse_answer(result, answer_model)


def run_cli(label: str, *, budget_s: float, fn: Callable[[], BaseModel]) -> None:
    """Run a one-shot function with a spinner and print the typed result as JSON."""
    started = time.monotonic()
    print(f"{label} starting…", file=sys.stderr)
    with progress_spinner(f"{label} running", budget_s=budget_s):
        result = fn()
    print(f"completed in {time.monotonic() - started:.1f}s", file=sys.stderr)
    print(result.model_dump_json(indent=2))


def run_dict_cli(label: str, *, budget_s: float, fn: Callable[[], dict[str, Any]]) -> None:
    """Like ``run_cli`` but for tools that return a free-form ``dict`` (``extract``)."""
    started = time.monotonic()
    print(f"{label} starting…", file=sys.stderr)
    with progress_spinner(f"{label} running", budget_s=budget_s):
        result = fn()
    print(f"completed in {time.monotonic() - started:.1f}s", file=sys.stderr)
    print(json.dumps(result, indent=2))
