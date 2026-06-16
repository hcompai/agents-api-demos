# Skills

This repo doubles as a **Claude Code plugin marketplace** ([`.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json)): each skill is published as a plugin under the `hai-skills` marketplace, so anyone can install them into their own Claude Code without cloning the repo.

## Available skills

| Skill | What Claude learns | Pairs with |
| --- | --- | --- |
| [`hai-agents`](hai-agents/) | The H Company APIs end-to-end: portal (auth, orgs, API keys + the automated `HAI_API_KEY` → `.env` login script), agent platform v2 (sessions, agents, environments, vaults, long-polling), the hai-agents Python/TS SDKs, and the agent-view run-replay workflow | any project calling the H Company platform |
| [`hai-qa-via-cli`](hai-qa-via-cli/) | When and how to invoke `qa-cli review` / `qa-cli visual` to QA a live web page and surface the structured findings | the [`qa/cli`](../examples/qa/cli/) example in this repo |

## Install in Claude Code

In any Claude Code session:

```
/plugin marketplace add hcompai/hai-agents-demos      # or a local clone path
/plugin install hai-agents@hai-skills
/plugin install hai-qa-via-cli@hai-skills
```

Once installed, the skills trigger automatically when a conversation matches their `description` — e.g. asking about H Company sessions or API keys pulls in `hai-agents`.

## Add a new skill

1. Create `skills/<your-skill>/SKILL.md` with `name` and `description` frontmatter (keep the description specific — it's what triggers the skill).
2. Add reference docs or scripts alongside it as needed (see [`hai-agents/references/`](hai-agents/references/) for the pattern).
3. Register it as a plugin entry in [`.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json).
