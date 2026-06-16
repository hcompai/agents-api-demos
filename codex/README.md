# Run the demos inside Codex

The same `hai-agents-demos`, with [OpenAI Codex CLI](https://developers.openai.com/codex/) as the
host. Like Claude Code and Hermes, Codex is an MCP client, so the SDK code is unchanged; only the
config format differs.

| Host | MCP config |
| --- | --- |
| Claude Code | `.mcp.json` |
| Hermes Agent | `~/.hermes/config.yaml` |
| Codex | `~/.codex/config.toml` (or project `.codex/config.toml`) |

## Prerequisites

This repo installed (see the [root README](../README.md)): `uv sync`, with `HAI_API_KEY` in `.env`.

## 1. Install Codex

```bash
npm install -g @openai/codex   # see the Codex docs for other install options
```

## 2. Register the servers

Copy the tables from [`config.toml.example`](config.toml.example) into `~/.codex/config.toml`
(or a project-scoped `.codex/config.toml` in a trusted project) and set `cwd` to your clone's path.
The hosted `hai-agents-platform` server reads the `hk-` key from `HAI_API_KEY` via
`bearer_token_env_var`, so export it first; the stdio demo servers load `.env` themselves.

```bash
export HAI_API_KEY=hk-...
```

`codex mcp add` is the CLI alternative if you'd rather not edit the file by hand.

## 3. Verify

```bash
codex mcp list      # shows the three servers
```

## Notes

- **Timeouts.** Codex's defaults are tight (10 s startup, 60 s per tool). The example raises both:
  `startup_timeout_sec = 60` (the first `uv run` resolves dependencies) and `tool_timeout_sec = 420`
  (`review_web_ui` runs up to 360 s).
- **Tools and secrets** (Codex best practice). The QA server is scoped with `enabled_tools`, and
  credentials stay out of the file (the hosted server via `bearer_token_env_var`, the stdio servers
  via `.env`). Tighten `enabled_tools`, or add `disabled_tools`, for any server exposing more than
  you need; the extract server ships all ~11 tools by design.
- **Region.** The hosted server uses EU (the demos' SDK default); swap to `agp.hcompany.ai` for US.
- **Project context.** Codex reads the repo's `AGENTS.md`; it doesn't use agentskills.io skills, so
  `hai-platform` and `hai-qa-via-cli` don't carry over (only the MCP servers do).
- Not verified live here (Codex wasn't installed). If `config.toml` servers don't load, see
  [openai/codex#3441](https://github.com/openai/codex/issues/3441).
