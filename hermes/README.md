# Run the demos inside Hermes Agent

The same `hai-agents-demos`, with [Hermes Agent](https://hermes-agent.nousresearch.com)
(Nous Research's open-source agent harness) as the host instead of Claude Code.

Nothing about the SDK or the agents changes. Hermes consumes the same three interfaces these
demos already expose: MCP servers, agentskills.io skills, and plain shell commands. This is
purely host wiring. Where Claude Code reads `.mcp.json`, Hermes reads `~/.hermes/config.yaml`.

| In Claude Code | In Hermes Agent |
| --- | --- |
| `.mcp.json` → `hai-agents-demos-qa`, `...-extract-anything` | `~/.hermes/config.yaml` `mcp_servers:` ([config.example.yaml](config.example.yaml)) |
| `skills/hai-qa-via-cli`, `skills/hai-agents` | `~/.hermes/skills/...` (agentskills.io format, same `SKILL.md`) |
| `qa-cli` / `extract-cli` / `counterfeit-cli` | identical shell commands |

## Prerequisites

This repo, installed the usual way (see the [root README](../README.md)):

```bash
uv sync
cp .env.example .env          # add HAI_API_KEY from https://platform.hcompany.ai/settings/api-keys
```

## 1. Install Hermes Agent + MCP support

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash   # Linux / macOS / WSL2
cd ~/.hermes/hermes-agent && uv pip install -e ".[mcp]"              # enable MCP transports
```

> MCP support ships as an extra. Without `[mcp]` installed, the `mcp_servers:` block is
> silently ignored.

## 2. Register the MCP servers

Hermes' baseline method (per the [MCP docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp))
is editing the `mcp_servers:` block in `~/.hermes/config.yaml` directly. For these demos that
is also the safest path, because it sets the required `timeout` in the same block. A
`review_web_ui` call runs a full cloud browser session that exceeds Hermes' 120 s default, and
without the bump it gets killed silently (see [Troubleshooting](#troubleshooting)).

Copy the block from [`config.example.yaml`](config.example.yaml) into `~/.hermes/config.yaml`,
then replace `/ABSOLUTE/PATH/TO/agent-sdk-demo` with your clone's path (`pwd` from the repo
root prints it). It uses `uv run --directory <repo>` plus an absolute `--env-file`, which fixes
the one real gotcha: Claude Code's relative `--env-file .env` won't resolve from Hermes'
`~/.hermes` working directory.

The `hermes mcp add` CLI is a convenient alternative (`--args` captures the rest of the line),
but it writes only `command`/`args`, so you set the timeout separately:

```bash
REPO="$(pwd)"   # run from the repo root
hermes mcp add hai-agents-demos-qa               --command uv --args run --directory "$REPO" --env-file "$REPO/.env" hai-agents-demos-qa
hermes mcp add hai-agents-demos-extract-anything --command uv --args run --directory "$REPO" --env-file "$REPO/.env" hai-agents-demos-extract-anything
hermes config set mcp_servers.hai-agents-demos-qa.timeout 420
hermes config set mcp_servers.hai-agents-demos-extract-anything.timeout 420
```

### Also register the generic platform server

The two servers above are this repo's typed recipes. To drive any H agent, also register the
hosted agent-platform server, `io.github.hcompai/hai-agents`: a streamable-HTTP proxy over
`/api/v2`, `hk-`-key auth, exposing `run_agent`, `wait_for_session`, `list_agents`,
`send_message`, `cancel_session`, `share_session`.

```bash
hermes mcp add hai-agents-platform --url https://agp.eu.hcompany.ai/mcp --auth header
# set the header to: Authorization: Bearer hk-...   (US endpoint: https://agp.hcompany.ai/mcp)
```

Config-block form (it stores the key in the file) is in [`config.example.yaml`](config.example.yaml).
`run_agent` caps its wait at ~24 s, then returns a handle to poll with `wait_for_session`, so the
`timeout` bump applies for long tasks.

## 3. Verify

```bash
hermes mcp test hai-agents-demos-qa     # MCP handshake + tools/list; no cloud session, no cost
```

It should report `review_web_ui` and `visual_check`. Inside a `hermes chat` session you can
also `/reload-mcp` and ask "what tools do you have?". You should additionally see `extract`,
`describe_picture_of_the_day`, and the `get_*` tools.

> **Name normalization.** Hermes rewrites hyphens and dots to underscores in server names, so
> `hai-agents-demos-qa` is surfaced as `hai_agents_demos_qa`. Tool names like `review_web_ui` are
> already valid identifiers and stay as-is.

## 4. First slice: QA a page

```
Use review_web_ui to check https://news.ycombinator.com and verify the top story
link works and the page has reasonable accessibility.
```

Hermes calls the tool, the `hai-agents` SDK drives a cloud browser, and you get back a
structured `{verdict, summary, findings}`. For a subject with known issues, point it at the
intentionally broken page in [`examples/broken_ui/`](../examples/broken_ui/).

## Skills (optional)

Both skills have Hermes-adapted entry docs under `hermes/skills/`, in agentskills.io format:

```bash
mkdir -p ~/.hermes/skills/hai
cp -r  hermes/skills/hai-qa-via-cli ~/.hermes/skills/hai/hai-qa-via-cli   # self-contained
cp -RL hermes/skills/hai-agents   ~/.hermes/skills/hai/hai-agents     # -L dereferences its symlinks (see below)
# then restart Hermes; it re-scans ~/.hermes/skills/
```

`hai-qa-via-cli` is forked to invoke the CLI with `uv run --directory <repo>`. For `hai-agents`,
only the `SKILL.md` is Hermes-adapted (frontmatter, where `h_login.py` runs, and writing the key
into the demo repo's `.env`); its `references/` and `scripts/` are symlinks into the canonical
`skills/hai-agents/`, so there's no duplication and `cp -RL` copies the real files. (The
symlinks need a symlink-aware checkout: macOS, Linux, or WSL2.)

## CLI demos

The CLI entry points (`qa-cli`, `extract-cli`, `counterfeit-cli`) are plain shell commands, so
Hermes can run them through its built-in shell tools with no registration at all. This is the
only way to reach [`counterfeit_detection`](../examples/counterfeit_detection/), which is
CLI-only (local Playwright plus Holo visual compare):

```bash
HAI_DEMOS="$(pwd)"   # from the repo root
uv run --directory "$HAI_DEMOS" --env-file "$HAI_DEMOS/.env" counterfeit-cli sweep --genuine-url "https://..."
```

## Notes on the host model

Hermes is model-agnostic (any OpenAI-compatible endpoint; Hermes 3/4 are purpose-built for tool
use) and wants at least 64k context for multi-step tool loops. The bar on the host model is low
here: the browser-agent reasoning runs in the H cloud via the SDK, and Hermes only decides when
to call a tool and reads the result.

## Troubleshooting

- **The answer says "the tool timed out, so I verified directly" (or isn't a structured
  `ReviewResult`).** The call exceeded Hermes' default 120 s per-call timeout (`mcp_tool.py`),
  so Hermes killed it and fell back to its own web tools. A `review_web_ui` session runs up to
  360 s; set `timeout: 420` (step 2).
- **The tools don't show up after `/reload-mcp`.** Two common causes: the `[mcp]` extra isn't
  installed (step 1), so `mcp_servers:` is ignored; or you're in an ACP session, where MCP tools
  may not register because `enabled_toolsets` is hardcoded
  ([hermes-agent#14986](https://github.com/NousResearch/hermes-agent/issues/14986)).
- **`HAI_API_KEY is not set`.** The server can't read the key. Check that the `--env-file` path
  in your config is absolute and points at the repo's `.env`.

## References

- [Hermes Agent docs](https://hermes-agent.nousresearch.com/docs/) ·
  [MCP feature](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp) ·
  [MCP config reference](https://hermes-agent.nousresearch.com/docs/reference/mcp-config-reference) ·
  [Skills system](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills)
