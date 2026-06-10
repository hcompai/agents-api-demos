"""Shared agent definition components used across the example servers."""

import os
from pathlib import Path
from typing import Literal

from hai_agents import Environment_Web
from pydantic import BaseModel

_PROMPTS_DIR = Path(__file__).parent / "prompts"
AGENT_SKILLS_DIR = Path(__file__).parent / "agent_skills"

REVIEWER_INSTRUCTIONS: str = (_PROMPTS_DIR / "reviewer_instructions.md").read_text()


class ReviewResult(BaseModel):
    verdict: Literal["pass", "warning", "fail"]
    summary: str
    findings: list[str] = []
    """Each item is a human-readable string formatted ``[severity · area] issue. Suggestion: ...``."""
    steps_taken: list[str] = []


def browser_env(start_url: str) -> Environment_Web:
    """Build the inline cloud web environment a tool drives.

    A catalog-id ``str`` would also be valid in ``Agent.environments`` (the env-agnostic
    seam), but every shipped example today binds to an inline headless browser.

    ``mode`` is left unset (``None``) so it is omitted from the wire and the server applies its
    own default (currently ``visual``). Omitting keeps us forward-compatible if the field's
    values change, and avoids pinning a default the backend owns.

    Args:
        start_url: The URL the browser should navigate to as it boots the session.

    Returns:
        A configured ``Environment_Web`` object ready to slot into ``Agent.environments``.
    """
    return Environment_Web(
        id="browser",
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


def load_agent_skills() -> list[dict]:
    """Load all skill markdown files from the shared ``agent_skills/`` directory."""
    if not AGENT_SKILLS_DIR.is_dir():
        return []
    return [_parse_skill_file(path) for path in sorted(AGENT_SKILLS_DIR.glob("*.md"))]


def _parse_skill_file(path: Path) -> dict:
    text = path.read_text()
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: expected YAML frontmatter")
    frontmatter, _, body = text[4:].partition("\n---\n")
    fields = {}
    for line in frontmatter.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    try:
        return {"name": fields["name"], "description": fields["description"], "body": body.strip()}
    except KeyError as exc:
        raise ValueError(f"{path}: missing field {exc.args[0]!r} in frontmatter") from exc
