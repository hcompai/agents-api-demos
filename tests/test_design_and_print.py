"""Check print-session outcomes without controlling a desktop or printer."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hai_agents import SessionRunResult

from examples.design_and_print.main import design_and_print


class PrintSessionTest(unittest.TestCase):
    def test_only_completed_sessions_succeed(self) -> None:
        with (
            TemporaryDirectory() as jobs,
            patch("examples.design_and_print.main.JOBS_DIR", Path(jobs)),
            patch("examples.design_and_print.main.require_api_key", return_value="test"),
            patch("examples.design_and_print.main.Client.local"),
            patch("examples.design_and_print.main.run_session_streaming") as run,
        ):
            for status in ("failed", "timed_out", "interrupted", "idle"):
                run.return_value = SessionRunResult(
                    id="test", status=status, answer="Print result", events=[], next_from_index=0
                )
                with (
                    self.subTest(status=status),
                    redirect_stdout(io.StringIO()) as output,
                    redirect_stderr(io.StringIO()),
                    self.assertRaisesRegex(RuntimeError, f"status={status}"),
                ):
                    design_and_print("A rook", "Test printer")
                self.assertEqual(output.getvalue(), "")

            run.return_value = SessionRunResult(
                id="test", status="completed", answer="Print result", events=[], next_from_index=0
            )
            with redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()):
                design_and_print("A rook", "Test printer")
            self.assertEqual(output.getvalue().strip(), "Print result")


if __name__ == "__main__":
    unittest.main()
