"""Shared agent definition components used by both the qa_mcp and qa_cli examples."""

from pathlib import Path
from typing import Literal

from hai_agents.polling import SessionRunResult
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


def browser_env(start_url: str) -> dict:
    """Return a web environment config dict seeded at ``start_url``."""
    return {
        "id": "browser",
        "kind": "web",
        "headless": True,
        "width": 1280,
        "height": 800,
        "start_url": start_url,
    }


def load_agent_skills() -> list[dict]:
    """Load all skill markdown files from the shared ``agent_skills/`` directory."""
    if not AGENT_SKILLS_DIR.is_dir():
        return []
    return [_parse_skill_file(path) for path in sorted(AGENT_SKILLS_DIR.glob("*.md"))]


def answer_from_events(result: SessionRunResult) -> dict | None:
    """Fallback: extract the structured answer from the policy_event in the event stream.

    The platform stores the answer on the trajectory row when it processes the policy_event
    that contains the answer tool_req. Until that change is deployed, result.answer is None
    even on successful structured-output sessions, so we read the answer directly from the
    events the SDK already fetched.
    """
    for event in reversed(result.events):
        if event.type != "AgentEvent":
            continue
        # The API's to_model() unwraps the inner event so event.data IS the inner dict
        # (kind, tool_reqs, …) — there is no extra "event" wrapper at this layer.
        inner = event.data if isinstance(event.data, dict) else None
        if not isinstance(inner, dict) or inner.get("kind") != "policy_event":
            continue
        for req in inner.get("tool_reqs") or []:
            if isinstance(req, dict) and req.get("tool_name") == "answer":
                args = req.get("args")
                if args is not None:
                    return args
    return None


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
