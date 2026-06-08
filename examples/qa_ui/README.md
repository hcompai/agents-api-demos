# `qa_ui` — QA a web UI from Claude Code

A FastMCP server that exposes two tools to Claude Code, both backed by a `hai-agents` browser agent.

## Tools

- **`review_web_ui(url, instruction) -> ReviewResult`** — runs a full reviewer agent and returns `{verdict, summary, findings[], steps_taken[]}`.
- **`visual_check(url, question) -> str`** — opens a URL, takes a couple of observation steps, returns a short free-text answer.

## Example prompts

In Claude Code, with the MCP server registered:

- *"Use `review_web_ui` to check https://news.ycombinator.com — verify the top story link works and the page has reasonable accessibility."*
- *"Use `visual_check` on https://example.com — what color is the main heading?"*

## How it works

`server.py` defines an inline agent and calls `run_session` on each tool invocation:

```python
result = run_session(
    client,
    agent={
        "name":         "ui-reviewer",
        "instructions": REVIEWER_INSTRUCTIONS,  # baked-in QA system prompt
        "skills":       _load_agent_skills(),   # reusable docs from agent_skills/
        "environments": [{"kind": "web", "start_url": url, ...}],
    },
    messages=instruction,
    max_steps=25,
    max_time_s=360.0,
    answer_format=ReviewResult.model_json_schema(),  # forces structured output
)
```

Three SDK primitives carry the demo: an **inline agent definition** (no pre-registered template needed), a **web environment** that seeds the agent's browser at `url`, and **`answer_format`** which constrains the response to a JSON object that validates back into `ReviewResult`.

### Agent skills

Skills are named instruction documents the agent can load on demand. They live in [`../agent_skills/`](../agent_skills/) (shared with `qa_cli`) as markdown files with YAML frontmatter (`name`, `description`, body):

```
../agent_skills/
└── design-qa-checklist.md
```

The agent reads each skill's `description` to decide when to pull in the full `body`. To add a skill, drop a new `*.md` file in the directory — no code change needed.

> These are **not** Claude Code skills (`.claude/skills/`). Agent skills travel with the remote agent session; `.claude/skills/` contains instructions for the local Claude Code assistant.

## Running standalone

The same logic is also wired to a plain CLI in [`../qa_cli/`](../qa_cli/):

```bash
uv run qa-cli review --url https://example.com --instruction "focus on accessibility"
uv run qa-cli visual --url https://example.com --question "what color is the heading?"
```

To iterate quickly without going through Claude Code, use the debug entry point — it loads `.env` and enables verbose logging:

```bash
uv run debug-qa review --url https://news.ycombinator.com
uv run debug-qa visual --url https://example.com --question "what color is the heading?"
```
