"""CLI entry point — dispatches to subcommands defined alongside each function.

Every ``functions/<name>.py`` exposes a ``_cli`` subcommand and registers itself via
``CLI_NAME`` / ``CLI_FN``; the ``functions`` package aggregates them into
``CLI_SUBCOMMANDS``. This file is just the tyro wiring.

    uv run extract-cli                       # list all subcommands
    uv run extract-cli flight-options --help # flags for one tool
    uv run extract-cli picture               # vision-only demo, live event tail
"""

import sys

import tyro
from dotenv import load_dotenv

from examples._shared import setup_cli_logging
from examples.extract_anything.functions import CLI_SUBCOMMANDS


def main() -> None:
    """Entry point for the ``extract-cli`` console script."""
    load_dotenv()
    setup_cli_logging()
    try:
        tyro.extras.subcommand_cli_from_dict(CLI_SUBCOMMANDS)
    except RuntimeError as exc:
        sys.exit(f"error: {exc}")


if __name__ == "__main__":
    main()
