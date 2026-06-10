"""One-off: run a QA session and print the agent-view replay URL."""

import os
from pathlib import Path

# Load .env (KEY=VALUE lines) into the environment.
_env = Path(__file__).parent / ".env"
for _line in _env.read_text().splitlines():
    _line = _line.strip()
    if _line and not _line.startswith("#") and "=" in _line:
        _k, _, _v = _line.partition("=")
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from hai_agents import Client, run_session

from examples._shared import (
    REVIEWER_INSTRUCTIONS,
    ReviewResult,
    browser_env,
    load_agent_skills,
)

client = Client(api_key=os.environ["H_API_KEY"])

result = run_session(
    client,
    agent={
        "name": "ui-reviewer",
        "description": "Reviews a web UI for usability, accessibility, and obvious bugs.",
        "instructions": REVIEWER_INSTRUCTIONS,
        "skills": load_agent_skills(),
        "environments": [browser_env("https://news.ycombinator.com")],
    },
    messages=("Verify the top story link works and assess the page's accessibility. Return a structured verdict."),
    max_steps=25,
    max_time_s=360.0,
    answer_format=ReviewResult.model_json_schema(),
)

print("SESSION_ID:", result.id)
print("STATUS:", result.status)
print("REPLAY_URL: https://platform.hcompany.ai/agent-view/" + result.id)
