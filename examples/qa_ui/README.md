# `qa_ui` — QA a web UI from Claude Code

A FastMCP server that exposes two tools to Claude Code, both backed by a `hai-agents` browser agent.

## Tools

- **`review_web_ui(url, instruction) -> ReviewResult`** — runs a full reviewer agent and returns `{verdict, summary, findings[], steps_taken[]}`.
- **`visual_check(url, question) -> str`** — opens a URL, takes a couple of observation steps, returns a short free-text answer.

## Example prompts

In Claude Code, with the MCP server registered:

- *"Use `review_web_ui` to check https://news.ycombinator.com — verify the top story link works and the page has reasonable accessibility."*
- *"Use `visual_check` on https://example.com — what color is the main heading?"*

## Debugging

When something is off, drive the tools without going through Claude Code:

```bash
uv run debug-qa review --url https://news.ycombinator.com
uv run debug-qa visual --url https://example.com --question "what color is the heading?"
```

The script loads `.env`, runs at `DEBUG` log level (stderr), and prints the result on stdout.

## How the SDK is used

```python
result = run_session(
    client,
    agent={
        "name": "ui-reviewer",
        "description": "Reviews a web UI for usability, accessibility, and obvious bugs.",
        "environments": [{"id": "browser", "kind": "web", "headless": True, "width": 1280, "height": 800, "start_url": url}],
    },
    messages=instruction,
    max_steps=25,
    max_time_s=360.0,
    answer_format=ReviewResult.model_json_schema(),
)
```

Two SDK primitives carry the demo: an **inline agent definition** with a web environment, and **`answer_format`** so the agent returns a dict that validates back into `ReviewResult`.
