"""QA-specific agent components shared between the MCP server and the CLI entry points."""

from pathlib import Path
from typing import Literal

from hai_agents import AgentSkillsItem, Skill
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
