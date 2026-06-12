"""Shared plumbing for the deterministic extract_anything functions.

This module owns the framework-level state — the FastMCP instance, the lazy SDK client,
the cross-host-safe ``Price`` type, an answer-parser, and the runner / CLI helpers. Each
``functions/<name>.py`` module imports what it needs from here, so the three surfaces
(Python function, ``@mcp.tool``, CLI subcommand) for one tool all live in the same file
as the function itself.

``server.py`` and ``cli.py`` end up as ~25-line orchestrators.
"""

import contextlib
import json
import sys
import threading
import time
from decimal import Decimal
from typing import IO, Annotated, Any, Callable, Iterator, TypeVar

from fastmcp import FastMCP
from hai_agents import Agent, Client, SessionRunResult, run_session
from pydantic import BaseModel, HttpUrl, TypeAdapter, WithJsonSchema

from examples._shared import browser_env, require_api_key
from examples.extract_anything.prompts import OPERATOR_INSTRUCTIONS

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
    """Build an agent, run a session, validate the answer into ``answer_model``.

    ``persona`` is the per-tool system-prompt line ("You operate flight-search UIs."); the
    shared ``OPERATOR_INSTRUCTIONS`` (loaded from ``prompts/extractor_instructions.md``)
    is appended automatically so per-tool callers don't restate the JSON / no-invent /
    no-markdown rules.
    """
    result = run_session(
        client,
        agent=Agent(
            name=name,
            description=description,
            instructions=f"{persona}\n\n{OPERATOR_INSTRUCTIONS}",
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


@contextlib.contextmanager
def progress_spinner(
    label: str,
    *,
    budget_s: float | None = None,
    stream: IO[str] = sys.stderr,
) -> Iterator[None]:
    """Background heartbeat for long-running blocking calls like ``run_session``.

    Inlined here so this example stays self-contained; the version that used to live in
    ``examples/_shared.py`` was removed when no other example needed it. On a TTY this
    animates a braille frame + elapsed seconds on a single line; on a piped stream it
    falls back to a heartbeat line every 10s.
    """
    frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    stop = threading.Event()
    started = time.monotonic()
    is_tty = hasattr(stream, "isatty") and stream.isatty()

    def _tick() -> None:
        i = 0
        next_heartbeat = 10.0
        while not stop.wait(0.15 if is_tty else 1.0):
            elapsed = time.monotonic() - started
            budget = f" / {budget_s:.0f}s" if budget_s else ""
            if is_tty:
                stream.write(f"\r{frames[i % len(frames)]} {label} {elapsed:.0f}s{budget}")
                stream.flush()
                i += 1
            elif elapsed >= next_heartbeat:
                stream.write(f"{label} ... {elapsed:.0f}s{budget}\n")
                stream.flush()
                next_heartbeat += 10.0

    worker = threading.Thread(target=_tick, daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join(timeout=0.5)
        if is_tty:
            stream.write("\r\033[K")  # erase the spinner line so it doesn't bleed into the next output
            stream.flush()
