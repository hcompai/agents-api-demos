# `qa_cli` — QA a web UI via a CLI + Claude Code skill

Same SDK calls as [`qa_ui`](../qa_ui/), different interface. Where `qa_ui` exposes the agent as an **MCP server**, this example exposes it as a **shell command** and uses a Claude Code **skill** to teach Claude when to invoke it.

## CLI

```bash
uv run qa-cli review --url https://example.com --instruction "look for broken links"
uv run qa-cli visual --url https://example.com --question "what color is the heading?"
```

- `review` prints a `ReviewResult` JSON on stdout (verdict, summary, findings, steps_taken).
- `visual` prints a short free-text answer.
- Progress logs go to stderr.

## Skill

The skill lives at [`.claude/skills/qa-via-cli/SKILL.md`](../../.claude/skills/qa-via-cli/SKILL.md). Claude Code picks it up automatically and triggers when the user asks to QA a URL or get a quick visual answer about a page.

> *"QA https://example.com for accessibility issues."*

Claude invokes the CLI via Bash, parses stdout, and surfaces findings in chat.

## How it differs from `qa_ui`

| Aspect | `qa_ui` (MCP) | `qa_cli` (CLI + skill) |
| --- | --- | --- |
| Wiring | `.mcp.json` registers an MCP server | `.claude/skills/qa-via-cli/SKILL.md` |
| Invocation in Claude | Native `mcp__...` tool call | Bash invocation of `qa-cli` |
| Result handling | Structured tool return | Claude parses stdout JSON |
| Runnable outside Claude | Need an MCP client | Just run the CLI |
| Server process | Yes (FastMCP, stdio) | No — one-shot subprocess |

Same agent definition, same prompt, same `answer_format`. Choose the surface that fits — MCP when you want a long-lived tool surface in Claude Code; CLI when you want a thing humans and scripts can run too.
