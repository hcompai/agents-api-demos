# `mcpify_anything` — typed-toolkit MCP server

A FastMCP server demonstrating the **typed-toolkit pattern**: one decorator declares many MCP tools, each with its own typed input + answer schema, all backed by a single shared runner driving a cloud browser CUA.

Where [`qa_mcp`](../qa_mcp/) shows wrapping *one* task as *one* tool, this shows building a **family** of typed tools off the same underlying agent — useful when you want a curated set of structured-output operations to expose to Claude Code.

## Tools

| Tool | Shape | What it shows |
| --- | --- | --- |
| `extract` | dynamic-schema escape hatch | Caller supplies a JSON Schema at call time — the framework wires it into the platform's `answer_format` per call. Use when no curated tool fits. |
| `get_product_prices` | typed read + capture metadata | The agent reports only what it can read off the page; the handler stamps a client-side `captured_at` timestamp. |
| `add_cart_items` | action + read-back proof + client-derived totals | The agent acts (adds to cart) and reads the cart back. The handler derives `cart_total`, `currency`, and a `status` (`added` / `partial` / `noop`) from the read-back lines. |

## Adding a tool

Drop a new module under [`tools/`](tools/) with a `@browser_tool`-decorated async function and append its spec to [`tools/__init__.py:SPECS`](tools/__init__.py).

```python
from pydantic import BaseModel, HttpUrl
from examples.mcpify_anything.tool import browser_tool


class JobListingsInput(BaseModel):
    site: HttpUrl
    role: str


class JobListing(BaseModel):
    title: str
    company: str
    location: str
    url: HttpUrl


@browser_tool(
    instructions="You operate job-search UIs.",
    site=lambda a: a.site,
    prompt=lambda a: f"On {a.site}, find listings for {a.role!r}.",
)
async def get_job_listings(args: JobListingsInput, answer: list[JobListing]) -> list[JobListing]:
    return answer
```

Three properties of the framework do all the work:

- **The signature is the contract.** `args: <InputModel>` becomes the MCP tool's input schema; `answer: <T>` becomes the platform's `answer_format`; the return type is what FastMCP exposes to the caller.
- **`schema_hint(answer_model)` is auto-appended** to the user message so per-tool prompts never restate the JSON shape.
- **`_OPERATOR_PREAMBLE`** is auto-prepended to every tool's `instructions` so per-tool strings stay pure persona / behavioural heuristics.

## How it works

```mermaid
flowchart LR
  user[You in Claude Code] -->|tool call| mcp[FastMCP server<br/>server.py]
  mcp -->|build RunSpec| reg[register_specs<br/>tool.py]
  reg -->|run| runner[CuaRunner<br/>runner.py]
  runner -->|create_session + answer_format| api[H Agent API]
  api -->|controls| browser[Cloud headless browser]
  browser -->|screenshots + DOM| api
  api -->|structured answer| runner
  runner -->|validated Pydantic| reg
  reg -->|tool output| user
```

## Run

```bash
cd agent-sdk-demo
uv sync
cp .env.example .env  # add H_API_KEY
agent-sdk-demo-mcpify-anything   # MCP server over stdio (Claude Code auto-registers via .mcp.json)
```

In Claude Code:

> *"Use `get_product_prices` on https://www.scrapingcourse.com/ecommerce/ — query 'jacket', max 5 results."*
>
> *"Use `add_cart_items` to add 2× https://www.scrapingcourse.com/ecommerce/product/abominable-hoodie/ — read back the cart."*
>
> *"Use `extract` on https://news.ycombinator.com to read the top 5 stories with answer_schema {…}."*

## Layout

```
mcpify_anything/
├── server.py                   # FastMCP wiring: build_server (DI) + compose_server + main()
├── config.py                   # env vars -> validated Settings
├── tool.py                     # @browser_tool decorator + register_specs registrar
├── runner.py                   # CuaRunner around async_wait_for_session (incl. CuaError)
├── schema_hint.py              # JSON-schema-to-prompt rendering
├── links.py                    # AGP base URL -> dashboard agent-view link
├── types.py                    # shared Price = Annotated[Decimal, WithJsonSchema(...)]
├── tools/
│   ├── __init__.py             # explicit SPECS tuple
│   ├── extract.py              # dynamic-schema escape hatch
│   ├── get_product_prices.py   # typed read with capture metadata
│   └── add_cart_items.py       # action + read-back proof + client totals
```

Tests live at the repo root in [`tests/mcpify_anything/`](../../tests/mcpify_anything/): a behavioural suite (fake Runner via DI) plus live integration tests under `integration/` (gated behind the `integration` marker).

## Configuration

| Env var | Required | Default | Source |
| --- | --- | --- | --- |
| `H_API_KEY` | yes | — | https://portal.hcompany.ai |
| `H_BASE_URL` | no | `HaiAgentsEnvironment.EU` | override only when targeting a different deployment |
| `H_AGENT_ARTIFACT` | no | `mcpify-anything-agent` | the published agent build matched to these prompts |
