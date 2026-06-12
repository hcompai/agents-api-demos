"""QA-specific agent components shared between the MCP server and the CLI entry points."""

from pathlib import Path
from typing import Literal

from hai_agents import Agent, AgentSkillsItem, Skill
from pydantic import BaseModel

from examples._shared import browser_env

_PROMPTS_DIR = Path(__file__).parent / "prompts"
AGENT_SKILLS_DIR = Path(__file__).parent / "agent_skills"

REVIEWER_INSTRUCTIONS: str = (_PROMPTS_DIR / "reviewer_instructions.md").read_text()
VISUAL_INSTRUCTIONS: str = "Open the page and answer the user's question in one or two sentences."


class ReviewResult(BaseModel):
    """Structured answer for the QA reviewer agent."""

    verdict: Literal["pass", "warning", "fail"]
    summary: str
    findings: list[str] = []
    """Each item is a human-readable string formatted ``[severity · area] issue. Suggestion: ...``."""
    steps_taken: list[str] = []


def build_reviewer_agent(url: str) -> Agent:
    """Build the ``ui-reviewer`` agent whose browser opens on ``url``.

    Returns the same agent definition shared by the MCP server, the CLI, and the debug runner —
    one place to update the QA reviewer's instructions, skills, and answer schema.
    """
    return Agent(
        name="ui-reviewer",
        description="Reviews a web UI for usability, accessibility, and obvious bugs.",
        instructions=REVIEWER_INSTRUCTIONS,
        skills=load_agent_skills(),
        environments=[browser_env(url)],
        answer_format=ReviewResult.model_json_schema(),
    )


def build_visual_checker_agent(url: str) -> Agent:
    """Build the ``visual-checker`` agent whose browser opens on ``url``."""
    return Agent(
        name="visual-checker",
        description="Answers a single visual question about a web page.",
        instructions=VISUAL_INSTRUCTIONS,
        environments=[browser_env(url)],
    )


def load_agent_skills() -> list[AgentSkillsItem]:
    """Load all skill markdown files from the ``agent_skills/`` directory next to this module."""
    if not AGENT_SKILLS_DIR.is_dir():
        return []
    return [_parse_skill_file(path) for path in sorted(AGENT_SKILLS_DIR.glob("*.md"))]


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
