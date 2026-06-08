# Examples

Each subdirectory is one self-contained recipe for the `hai-agents` SDK.

| Example | What it shows |
| --- | --- |
| [`qa_ui`](qa_ui/) | Run an autonomous browser agent against a remote URL to QA a web UI; expose it to Claude Code as an MCP server. |
| [`qa_cli`](qa_cli/) | Same QA agent, exposed as a shell command (`qa-cli`) and surfaced to Claude via the `qa-via-cli` skill instead of MCP. |

To add an example, create a new subdirectory with a `server.py` (or `main.py`), a short `README.md`, and — if it's an MCP server — register it in the root `.mcp.json`.
