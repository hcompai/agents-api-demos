"""Design-and-print CLI: a Holo agent on this Mac designs a part in FreeCAD and prints it from Bambu Studio.

    uv run --extra local print-cli --printer "My X2D" --prompt "A chess rook, about 25 mm tall"

Local agent mode: ``Client.local()`` runs the agent runtime and its desktop + workstation bridges on this machine.
See this folder's README.md.
"""

from __future__ import annotations

import shlex
import sys
import time
from pathlib import Path

import tyro
from dotenv import load_dotenv
from hai_agents import Agent, Client, Environment_Desktop, Environment_Workstation

from examples._shared import print_freeform_answer, require_api_key, run_session_streaming, setup_cli_logging

_HERE = Path(__file__).resolve().parent
JOBS_DIR = _HERE / "jobs"
INSTRUCTIONS = (_HERE / "instructions.md").read_text(encoding="utf-8")
RUNTIME_START_TIMEOUT_S = 180.0  # the local runtime's cold start can exceed the SDK's 45 s default on a busy Mac


def design_and_print(prompt: str, printer: str, max_steps: int = 300, max_time_s: float = 1500.0) -> None:
    """Design a part in FreeCAD, then slice and print it from Bambu Studio, all through the GUI.

    Args:
        prompt: What to design and print.
        printer: Printer name as shown in Bambu Studio's Print dialog.
        max_steps: Agent step budget.
        max_time_s: Agent time budget, in seconds.
    """
    require_api_key()
    JOBS_DIR.mkdir(exist_ok=True)
    started = time.monotonic()
    with Client.local(local_options={"timeout_s": RUNTIME_START_TIMEOUT_S}) as client:
        result = run_session_streaming(
            client,
            started=started,
            agent=Agent(
                name="design-and-print",
                description="Designs a part in FreeCAD and prints it from Bambu Studio.",
                model="holo4-27b",
                reasoning_effort="disabled",
                instructions=INSTRUCTIONS.replace("{jobs}", shlex.quote(str(JOBS_DIR))).replace("{printer}", printer),
                environments=[
                    Environment_Desktop(id="desktop", host="user_device"),
                    Environment_Workstation(id="workstation", host="user_device"),
                ],
            ),
            messages=prompt,
            max_steps=max_steps,
            max_time_s=max_time_s,
        )
    if result.status != "completed":
        raise RuntimeError(f"Print session ended with status={result.status}: {result.error or 'task unfinished'}")
    print_freeform_answer(result, started)


def main() -> None:
    """Entry point for the ``print-cli`` console script."""
    load_dotenv()
    setup_cli_logging()
    try:
        tyro.cli(design_and_print)
    except RuntimeError as exc:
        sys.exit(f"error: {exc}")


if __name__ == "__main__":
    main()
