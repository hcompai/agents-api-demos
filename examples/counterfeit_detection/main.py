"""Counterfeit-detection cookbook CLI: one agent, one task, three stages.

Input: the URL of a genuine product page. Output: counterfeit listing URL(s), or null.

    uv run counterfeit-cli simple --genuine-url "https://www.<brand>.com/<product>"
    uv run counterfeit-cli tooled --genuine-url "https://www.<brand>.com/<product>"
    uv run counterfeit-cli sweep  --genuine-url "https://www.<brand>.com/<product>" --max-steps 80 --max-time-s 1200

``simple`` is a bare ``run_session`` call. ``tooled`` adds two local custom tools (reference screenshots +
Holo visual compare). ``sweep`` adds a findings-stream tool and treats the step/time budget as fuel: find as
many counterfeits as it allows. See this folder's README.md for the full walkthrough.
"""

import json
import sys
import time
import typing
from typing import Literal

import httpx
import tyro
from dotenv import load_dotenv
from hai_agents import Agent, Client, SessionRunResult, Tool
from openai import OpenAI
from pydantic import BaseModel

from examples._shared import browser_env, print_structured_answer, require_api_key, setup_cli_logging
from examples.counterfeit_detection.local_tools import (
    MODELS_BASE_URL,
    FindingsLog,
    SnapshotStore,
    build_record_tool,
    build_visual_tools,
)
from examples.counterfeit_detection.prompts import (
    SIMPLE_INSTRUCTIONS,
    SIMPLE_TASK,
    SWEEP_INSTRUCTIONS,
    SWEEP_TASK,
    TOOLED_INSTRUCTIONS,
)

# A long-poll that read-times-out (or a brief connection drop) shouldn't kill a multi-minute run —
# the session keeps running server-side, so we resume the watch this many times before giving up.
_MAX_POLL_RETRIES = 6


class ProductInfo(BaseModel):
    """Genuine-product details extracted in Step 0 — grounds the queries, the price math, and the report."""

    model_name: str
    reference: str | None = None
    color: str | None = None
    material: str | None = None
    retail_price: str
    specifications: list[str] = []


class CounterfeitFinding(BaseModel):
    """Structured answer for the single-hit stages (``simple`` and ``tooled``)."""

    counterfeit_url: str | None
    confidence: Literal["high", "medium", "low", "none"]
    red_flags: list[str] = []
    reasoning: str
    product_info: ProductInfo | None = None


class SweepSummary(BaseModel):
    """Structured answer for ``sweep`` — the findings themselves arrive via ``record_counterfeit``."""

    recorded_count: int
    stopped_reason: Literal["budget_exhausted", "no_more_leads"]
    summary: str


def simple(genuine_url: str) -> None:
    """Stage 1 — a bare run_session call: find ONE counterfeit listing, or report none.

    Args:
        genuine_url: URL of the genuine product page the agent uses as its reference.
    """
    started = time.monotonic()
    result = _run_watched(
        _client(),
        agent=Agent(
            name="counterfeit-spotter",
            description="Finds one counterfeit listing of a genuine product.",
            instructions=SIMPLE_INSTRUCTIONS,
            environments=[browser_env(genuine_url)],
            answer_format=CounterfeitFinding.model_json_schema(),
        ),
        messages=SIMPLE_TASK.format(genuine_url=genuine_url),
        max_steps=40,
        max_time_s=600.0,
    )
    print_structured_answer(result, CounterfeitFinding, started)


def tooled(genuine_url: str) -> None:
    """Stage 2 — same task, plus local screenshot + visual-compare tools for grounded verdicts.

    Args:
        genuine_url: URL of the genuine product page the agent snapshots and compares against.
    """
    started = time.monotonic()
    store = SnapshotStore()
    result = _run_watched(
        _client(),
        agent=Agent(
            name="counterfeit-spotter",
            description="Finds one counterfeit listing, visually verified against cached references.",
            instructions=TOOLED_INSTRUCTIONS,
            environments=[browser_env(genuine_url)],
            answer_format=CounterfeitFinding.model_json_schema(),
        ),
        messages=SIMPLE_TASK.format(genuine_url=genuine_url),
        tools=build_visual_tools(store, _models_client()),
        max_steps=60,
        max_time_s=900.0,
    )
    print(f"reference screenshots saved: {len(store.items)}", file=sys.stderr)
    print_structured_answer(result, CounterfeitFinding, started)


def sweep(genuine_url: str, max_steps: int = 80, max_time_s: float = 1200.0) -> None:
    """Stage 3 — budget as fuel: record as many distinct counterfeits as max_steps/max_time_s allow.

    Args:
        genuine_url: URL of the genuine product page.
        max_steps: Step budget for the session; the agent is told to spend it.
        max_time_s: Wall-clock budget in seconds for the session.
    """
    started = time.monotonic()
    store = SnapshotStore()
    log = FindingsLog()
    result = _run_watched(
        _client(),
        agent=Agent(
            name="counterfeit-sweeper",
            description="Enumerates as many counterfeit listings as the budget allows.",
            instructions=SWEEP_INSTRUCTIONS,
            environments=[browser_env(genuine_url)],
            answer_format=SweepSummary.model_json_schema(),
        ),
        messages=SWEEP_TASK.format(genuine_url=genuine_url),
        tools=[*build_visual_tools(store, _models_client()), build_record_tool(log)],
        max_steps=max_steps,
        max_time_s=max_time_s,
    )
    _print_sweep_result(result, log, started)


def _client() -> Client:
    return Client(api_key=require_api_key())


def _models_client() -> OpenAI:
    return OpenAI(base_url=MODELS_BASE_URL, api_key=require_api_key())


def _run_watched(
    client: Client, *, tools: typing.Sequence[Tool] | None = None, **create_params: typing.Any
) -> SessionRunResult:
    """``run_session`` split open so the session id is printed the moment it exists.

    The platform link is the same for watching the agent act live and replaying the
    finished trajectory, so it is printed once at start and once after completion.

    The agent runs server-side; the client just long-polls for changes. A transient network
    blip (``httpx.ReadTimeout`` / connection reset) on a single poll otherwise crashes the whole
    run even though the session is fine — so we resume the wait, which re-polls from the session's
    current state. Already-answered tool calls are not re-dispatched (the server only advertises
    still-pending ones).
    """
    handle = client.start_session(tools=tools, **create_params)
    url = f"https://platform.hcompany.ai/agent-view/{handle.id}"
    print(f"session {handle.id}\nwatch live: {url}", file=sys.stderr, flush=True)
    for attempt in range(1, _MAX_POLL_RETRIES + 1):
        try:
            result = handle.wait_for_completion()
            break
        except httpx.TransportError as exc:  # ReadTimeout, ConnectError, RemoteProtocolError, …
            if attempt == _MAX_POLL_RETRIES:
                raise
            print(
                f"poll dropped ({type(exc).__name__}); agent still running server-side, "
                f"resuming watch [{attempt}/{_MAX_POLL_RETRIES - 1}]",
                file=sys.stderr,
                flush=True,
            )
    print(f"replay: {url}", file=sys.stderr)
    return result


def _print_sweep_result(result: SessionRunResult, log: FindingsLog, started: float) -> None:
    """Print sweep telemetry to stderr and the merged findings + agent summary to stdout."""
    print(
        f"completed in {time.monotonic() - started:.1f}s (status={result.status}, findings={len(log.items)})",
        file=sys.stderr,
    )
    summary = SweepSummary.model_validate(result.answer).model_dump() if isinstance(result.answer, dict) else None
    print(json.dumps({"findings": log.items, "agent_summary": summary}, indent=2))


def main() -> None:
    """Entry point for the ``counterfeit-cli`` console script."""
    load_dotenv()
    setup_cli_logging()
    try:
        tyro.extras.subcommand_cli_from_dict({"simple": simple, "tooled": tooled, "sweep": sweep})
    except RuntimeError as exc:
        sys.exit(f"error: {exc}")


if __name__ == "__main__":
    main()
