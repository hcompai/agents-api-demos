# Examples

Each subdirectory is one self-contained recipe for the `hai-agents` SDK.

| Example | What it shows |
| --- | --- |
| [`qa_mcp`](qa_mcp/) | Run an autonomous browser agent against a remote URL to QA a web UI; expose it to Claude Code as an MCP server. |
| [`qa_cli`](qa_cli/) | Same QA agent, exposed as a shell command (`qa-cli`) and surfaced to Claude via the `hai-qa-via-cli` skill instead of MCP. |
| [`mcpify_anything`](mcpify_anything/) | One MCP tool, `extract`: pass a URL, a natural-language task, and a JSON Schema; the cloud browser agent drives the page and returns JSON matching the schema. |
| [`counterfeit_detection`](counterfeit_detection/) | Cookbook for the single-agent + custom-tools pattern: find counterfeit listings of a genuine product. Three stages — a bare `run_session`, then local Playwright/Holo screenshot-compare tools, then a `max_steps`/`max_time_s` budget that turns "find one" into "find as many as the budget allows". |

To add an example, create a new subdirectory with a `server.py` (or `main.py`), a short `README.md`, and — if it's an MCP server — register it in the root `.mcp.json`.
