# `mcpify_anything` — one tool, any website

A FastMCP server with a **single MCP tool** that turns any URL into typed JSON. The caller supplies a JSON Schema at call time; a cloud browser agent drives the page and returns an answer the platform validates against that schema.

Where [`qa_mcp`](../qa_mcp/) shows wrapping *one fixed task* as one tool, this shows the inverse: one tool, **whatever shape the caller asks for**. Drop in a schema, get back JSON.

## The tool

```python
extract(url: str, task: str, answer_schema: dict) -> dict
```

| Arg | What it is |
| --- | --- |
| `url` | Page the browser agent starts on. |
| `task` | Natural-language instruction (no need to restate the JSON shape — the platform enforces `answer_schema`). |
| `answer_schema` | JSON Schema describing the desired return shape. Passed to the agent as `answer_format`. |

The whole tool is ~30 lines in [`server.py`](server.py) — read it top-to-bottom and you've seen the entire pattern: build an `Agent`, call `run_session`, return `result.answer`.

## Run

```bash
cd hai-agent-demos
uv sync
cp .env.example .env  # add H_API_KEY
hai-agent-demos-mcpify-anything   # MCP server over stdio (Claude Code auto-registers via .mcp.json)
```

In Claude Code:

> *"Use `extract` on https://news.ycombinator.com — task: `read the top 3 stories`, answer_schema: `{"type":"object","properties":{"stories":{"type":"array","items":{"type":"object","properties":{"title":{"type":"string"},"url":{"type":"string"}}}}}}`."*

## Layout

```
mcpify_anything/
├── server.py    # FastMCP wiring + the extract tool
└── README.md
```

## How it works

```mermaid
flowchart LR
  user[You in Claude Code] -->|extract(url, task, schema)| mcp[FastMCP server<br/>server.py]
  mcp -->|run_session<br/>answer_format=schema| api[H Agent API]
  api -->|controls| browser[Cloud headless browser]
  browser -->|screenshots + DOM| api
  api -->|JSON matching schema| mcp
  mcp -->|dict| user
```

## Configuration

| Env var | Required | Source |
| --- | --- | --- |
| `H_API_KEY` | yes | https://platform.hcompany.ai/settings/api-keys |
