# Examples

Each subdirectory is one self-contained recipe for the `hai-agents` SDK.

| Example | What it shows |
| --- | --- |
| [`qa_mcp`](qa_mcp/) | Run an autonomous browser agent against a remote URL to QA a web UI; expose it to Claude Code as an MCP server. |
| [`qa_cli`](qa_cli/) | Same QA agent, exposed as a shell command (`qa-cli`) and surfaced to Claude via the `qa-via-cli` skill instead of MCP. |
| [`mcpify_anything`](mcpify_anything/) | Turn any website into typed MCP tools. Each tool is a Pydantic input/output contract plus a one-line prompt; a cloud browser agent does the work and returns schema-validated JSON. Ships a typed read (`get_product_prices`), an action with read-back proof (`add_cart_items`), and a bring-your-own-schema escape hatch (`extract`). |

To add an example, create a new subdirectory with a `server.py` (or `main.py`), a short `README.md`, and — if it's an MCP server — register it in the root `.mcp.json`.
