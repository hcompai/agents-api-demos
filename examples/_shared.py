"""Shared agent definition components and entry-point helpers used across the example servers."""

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Literal

from hai_agents import AgentSkillsItem, Browser, SessionRunResult, Skill
from pydantic import BaseModel

_PROMPTS_DIR = Path(__file__).parent / "prompts"
AGENT_SKILLS_DIR = Path(__file__).parent / "agent_skills"
_LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"

REVIEWER_INSTRUCTIONS: str = (_PROMPTS_DIR / "reviewer_instructions.md").read_text()


class ReviewResult(BaseModel):
    verdict: Literal["pass", "warning", "fail"]
    summary: str
    findings: list[str] = []
    """Each item is a human-readable string formatted ``[severity · area] issue. Suggestion: ...``."""
    steps_taken: list[str] = []


def browser_env(start_url: str) -> Browser:
    """Build the inline cloud browser environment a tool drives.

    A catalog-id ``str`` would also be valid in ``Agent.environments`` (the env-agnostic
    seam), but every shipped example today binds to an inline headless browser.

    ``mode`` is left unset (``None``) so it is omitted from the wire and the server applies its
    own default (currently ``visual``). Omitting keeps us forward-compatible if the field's
    values change, and avoids pinning a default the backend owns.

    Args:
        start_url: The URL the browser should navigate to as it boots the session.

    Returns:
        A configured ``Browser`` object ready to slot into ``Agent.environments``.
    """
    return Browser(
        id="browser",
        kind="web",  # the API's environment union discriminates on this tag; the SDK doesn't default it
        headless=True,
        width=1280,
        height=800,
        start_url=start_url,
    )


def require_api_key() -> str:
    """Return ``H_API_KEY`` from the environment or raise with a remediation hint."""
    api_key = os.environ.get("H_API_KEY")
    if not api_key:
        raise RuntimeError(
            "H_API_KEY is not set. Copy .env.example to .env and add a key from "
            "https://platform.hcompany.ai/settings/api-keys, then re-run."
        )
    return api_key


def load_agent_skills() -> list[AgentSkillsItem]:
    """Load all skill markdown files from the shared ``agent_skills/`` directory."""
    if not AGENT_SKILLS_DIR.is_dir():
        return []
    return [_parse_skill_file(path) for path in sorted(AGENT_SKILLS_DIR.glob("*.md"))]


def setup_server_logging(level: int = logging.INFO) -> None:
    """Configure logging for an MCP server entry point.

    Logs go to stderr by default (Python's ``StreamHandler`` default), keeping stdout clean
    for the MCP stdio protocol.

    Args:
        level: Root logger level; defaults to ``INFO``.
    """
    logging.basicConfig(level=level, format=_LOG_FORMAT)


def setup_cli_logging(level: int = logging.WARNING, *, silence_http: bool = True) -> None:
    """Configure logging for a CLI entry point.

    Explicitly pins the stream to ``sys.stderr`` so stdout stays reserved for the JSON answer.

    Args:
        level: Root logger level; defaults to ``WARNING`` so CLI output stays uncluttered.
        silence_http: When ``True``, pin ``httpx``/``httpcore`` to ``WARNING`` regardless of
            the root level, so request-level chatter doesn't drown the JSON answer.
    """
    logging.basicConfig(level=level, stream=sys.stderr, format=_LOG_FORMAT)
    if silence_http:
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)


def print_structured_answer(result: SessionRunResult, model: type[BaseModel], started: float) -> None:
    """Print the session status to stderr and the validated answer JSON to stdout.

    Exits the process with a non-zero status if the session ended without a structured answer.

    Args:
        result: The completed ``run_session`` result.
        model: Pydantic model the answer must validate against.
        started: ``time.monotonic()`` timestamp captured before the session started.
    """
    print(f"completed in {time.monotonic() - started:.1f}s (status={result.status})", file=sys.stderr)
    if not isinstance(result.answer, dict):
        sys.exit(f"error: agent did not return a structured answer (status={result.status})")
    print(json.dumps(model.model_validate(result.answer).model_dump(), indent=2))


def print_freeform_answer(result: SessionRunResult, started: float) -> None:
    """Print the session status to stderr and a free-form answer (string or JSON) to stdout.

    Exits the process with a non-zero status if the session produced no answer.

    Args:
        result: The completed ``run_session`` result.
        started: ``time.monotonic()`` timestamp captured before the session started.
    """
    print(f"completed in {time.monotonic() - started:.1f}s (status={result.status})", file=sys.stderr)
    if result.answer is None:
        sys.exit(f"error: no answer (status={result.status})")
    print(result.answer if isinstance(result.answer, str) else json.dumps(result.answer))


def _parse_skill_file(path: Path) -> Skill:
    text = path.read_text()
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: expected YAML frontmatter")
    frontmatter, _, body = text[4:].partition("\n---\n")
    fields: dict[str, str] = {}
    for line in frontmatter.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    try:
        return Skill(name=fields["name"], description=fields["description"], body=body.strip())
    except KeyError as exc:
        raise ValueError(f"{path}: missing field {exc.args[0]!r} in frontmatter") from exc
