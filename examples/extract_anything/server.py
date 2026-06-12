"""FastMCP server entry point.

All the work happens in ``functions/`` — each tool module owns its ``@mcp.tool``
registration. Importing the ``functions`` package triggers those registrations as a
side effect; this file just configures logging and runs the server.
"""

from dotenv import load_dotenv

from examples._shared import setup_server_logging
from examples.extract_anything.functions._common import mcp

# Importing the functions package as a side effect registers every tool's ``@mcp.tool``.
# Using ``__import__`` (rather than a bound import) keeps the intent obvious and
# sidesteps unused-import warnings from ruff and Pylance.
__import__("examples.extract_anything.functions")


def main() -> None:
    """Entry point for the ``hai-agent-demos-extract-anything`` console script."""
    load_dotenv()
    setup_server_logging()
    mcp.run()


if __name__ == "__main__":
    main()
