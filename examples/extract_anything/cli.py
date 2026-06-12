"""Standalone CLI showing the deterministic-function-over-an-agent pattern.

The ``picture`` subcommand is a typed Python function — fixed prompt, fixed schema —
that internally runs a browser agent. The function itself lives in ``functions.py`` and
is shared with ``server.py``, which exposes it as an MCP tool. Same function, two
surfaces.

    uv run extract-cli picture          # vision-only: describe Wikipedia's Picture of the Day
"""

import sys
import time

import tyro
from dotenv import load_dotenv
from hai_agents import Client

from examples._shared import (
    print_structured_answer,
    require_api_key,
    run_session_streaming,
    setup_cli_logging,
)
from examples.extract_anything.functions import (
    PICTURE_MAX_STEPS,
    PICTURE_MAX_TIME_S,
    PICTURE_TASK,
    FeaturedPicture,
    picture_agent,
)


def picture() -> None:
    """Describe Wikipedia's Picture of the Day by actually looking at the image.

    Uses the streaming runner so the user sees a live tail of agent events. The MCP twin
    in ``server.py`` calls the same deterministic function with the one-shot runner.
    """
    started = time.monotonic()
    print("opening Wikipedia main page…", file=sys.stderr)
    result = run_session_streaming(
        _client(),
        started=started,
        agent=picture_agent(),
        messages=PICTURE_TASK,
        max_steps=PICTURE_MAX_STEPS,
        max_time_s=PICTURE_MAX_TIME_S,
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
