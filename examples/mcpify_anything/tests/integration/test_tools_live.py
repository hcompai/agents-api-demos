"""Live end-to-end tests against the H Agent Platform for the 3 shipped tools.

Gated behind ``RUN_SLOW_TESTS=1`` + ``H_API_KEY`` so the default ``pytest`` run never spends
real platform budget. ``_RecordingRunner`` captures the session id even when the run later
fails so ``_LinkBoard`` can print a dashboard URL for every case at module teardown.
"""

import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastmcp import Client
from hai_agents import Agent, AsyncClient, HaiAgentsEnvironment, Session

from examples.mcpify_anything.links import agent_view_url_from_id
from examples.mcpify_anything.runner import CuaRunner, RunSpec
from examples.mcpify_anything.server import build_server

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(not os.environ.get("RUN_SLOW_TESTS"), reason="set RUN_SLOW_TESTS=1"),
    pytest.mark.skipif(not os.environ.get("H_API_KEY"), reason="set H_API_KEY"),
]


@dataclass(frozen=True)
class LiveCase:
    """One end-to-end tool invocation against a real public site."""

    tool: str
    args: dict[str, Any]  # MCP tool input payload; shapes differ per tool, hence Any values
    check: Callable[[Any], None]  # validator over result.data; Pydantic shape differs per tool


_SCRAPINGCOURSE_HOODIE = "https://www.scrapingcourse.com/ecommerce/product/abominable-hoodie/"

# One case per shipped tool, all targeting ``scrapingcourse.com`` — a public no-login sandbox.
LIVE_CASES: tuple[LiveCase, ...] = (
    LiveCase(
        tool="get_product_prices",
        args={"site": "https://www.scrapingcourse.com/ecommerce/", "query": "hoodie", "max_results": 3},
        check=lambda data: _nonempty_field("products")(data),
    ),
    LiveCase(
        tool="add_cart_items",
        args={"items": [{"product_url": _SCRAPINGCOURSE_HOODIE, "quantity": 2}]},
        check=lambda data: _status_in("added", "partial", "noop")(data),
    ),
    LiveCase(
        tool="extract",
        args={
            "site": "https://www.scrapingcourse.com/ecommerce/",
            "task": ("Read the first product card on the home page and return its name and price exactly as shown."),
            "answer_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "price": {"type": "string"},
                },
                "required": ["name", "price"],
            },
        },
        check=lambda data: _dict_has_keys("name", "price")(data),
    ),
)


_LIVE_AGENT_ARTIFACT = os.environ.get("H_AGENT_ARTIFACT", "mcpify-anything-agent")


class _RecordingRunner(CuaRunner):
    """A real ``CuaRunner`` that remembers the created session id (and its own base URL).

    Lets ``_LinkBoard`` build a dashboard agent-view link for every run even when the run
    later times out or fails. Stashes ``base_url`` locally so the runner itself stays
    minimal (no public ``base_url`` accessor on production ``CuaRunner``).
    """

    def __init__(self, client: AsyncClient, base_url: str, agent_artifact: str) -> None:
        super().__init__(client, base_url, agent_artifact)
        self._base_url_for_links = base_url
        self.session_id: str | None = None

    async def _create_session(self, agent: Agent, spec: RunSpec[Any]) -> Session:
        created = await super()._create_session(agent, spec)
        self.session_id = created.id
        return created

    def link_for(self, sid: str) -> str:
        return agent_view_url_from_id(self._base_url_for_links, sid)


@dataclass
class _LinkBoard:
    links: dict[str, str] = field(default_factory=dict)

    def record(self, tool: str, runner: _RecordingRunner) -> None:
        if runner.session_id is not None:
            self.links[tool] = runner.link_for(runner.session_id)


@pytest.fixture(scope="module")
def link_board() -> Iterator[_LinkBoard]:
    # Prints collected links once at module teardown so a flaky/failed run is debuggable.
    board = _LinkBoard()
    yield board
    if board.links:
        lines = "\n".join(f"  {tool}: {link}" for tool, link in board.links.items())
        print(f"\n=== AGENT PLATFORM LINKS ===\n{lines}")


@pytest.mark.parametrize("case", LIVE_CASES, ids=lambda c: c.tool)
async def test_tool_live(case: LiveCase, link_board: _LinkBoard) -> None:
    runner = _RecordingRunner(
        AsyncClient(api_key=os.environ["H_API_KEY"]),
        HaiAgentsEnvironment.EU.value,
        _LIVE_AGENT_ARTIFACT,
    )
    try:
        async with Client(build_server(runner)) as client:
            result = await client.call_tool(case.tool, {"args": case.args})
        case.check(result.data)
    finally:
        # Record the link regardless of outcome: a created session is viewable even on failure.
        link_board.record(case.tool, runner)


def _nonempty_field(field_name: str) -> Callable[[Any], None]:
    # For receipt-style tools (``ProductPrices``, ...) ``result.data`` is a Pydantic-shaped
    # object; assert the named list field carries at least one row.
    def check(data: Any) -> None:
        rows = getattr(data, field_name)
        assert rows, f"expected a non-empty {field_name!r} from the live run, got {rows!r}"

    return check


def _status_in(*allowed: str) -> Callable[[Any], None]:
    def check(data: Any) -> None:
        assert data.status in allowed, f"unexpected status {data.status!r}, want one of {allowed}"

    return check


def _dict_has_keys(*keys: str) -> Callable[[Any], None]:
    # The ``extract`` tool returns a caller-shaped dict — assert every required key arrived
    # with a non-empty value, but stay schema-agnostic (callers pick their own keys).
    def check(data: Any) -> None:
        as_dict = dict(data)
        missing = [k for k in keys if k not in as_dict or as_dict[k] in (None, "", [])]
        assert not missing, f"expected keys {keys} populated, missing/empty {missing}, got {as_dict!r}"

    return check
