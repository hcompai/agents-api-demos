---
name: hai-agents
description: Expert knowledge of the two H Company backends — the portal (portal, API at portal.api.eu.hcompany.ai / portal.production.hcompany.ai — auth, organizations, API keys, invitations, billing) and the agent platform v2 API (agp.hcompany.ai — sessions, agents, skills, environments, vaults, long-polling, the hai-agents SDK). Use this skill whenever the user mentions portal, agent_platform, platform.hcompany.ai, agp.hcompany.ai, HAI_API_KEY or hk-... keys, hai-agents / hai_agents, run_session, agent sessions or trajectories, agent-view or replaying/reviewing a run, /api/v2 endpoints, browser agent environments, vaults for agent secrets, organizations or invitations on the H platform, the desktop OAuth/PKCE login flow, or wants to call, integrate with, debug, or automate anything against an H Company API — even without naming it (e.g. "get me an API key", "set up my .env", "launch a web agent", "why is my session stuck", "show me what the agent did", "why am I getting 401 from the platform?").
metadata:
  version: "1.0.1"
  author: hcompai
  repository: https://github.com/hcompai/agents-api-demos/skills
---

# H Company APIs (portal + agent platform)

H runs two backends, joined by one key. Figure out which you need — then **read the live docs, don't answer from this file's memory.** This skill is a router and a key-bootstrapper, not a copy of the docs: it deliberately holds almost no endpoint/param/field/limit/model detail, because hardcoding that here goes stale and has repeatedly been wrong.

| You're touching… | Backend | Base URL | Source of truth |
|---|---|---|---|
| Users, orgs, **API keys**, invitations, billing, STT | **Portal** | EU `https://portal.api.eu.hcompany.ai/api` · US `https://portal.production.hcompany.ai/api` | no public docs → [references/portal/](references/portal/) |
| **Running agents**: sessions, agents, skills, environments, vaults, events/long-poll, SDK, MCP | **Agent platform (agp)** — the public hub brands it the "Computer-Use Agent API" | EU (default) `https://agp.eu.hcompany.ai/api` · US `https://agp.hcompany.ai/api` | live docs + swagger (below) |

The **`hk-…` key** is *created* on the portal (by a logged-in user) and *consumed* by agp (`Authorization: Bearer hk-…`). "Get a key" → portal; "use a key" → agp. The full value is shown **only once at creation** — to "retrieve" one, make a new key and revoke the old.

`https://platform.hcompany.ai` is the product **frontend** (API-keys UI at `/settings/api-keys`), not an API.

## Before anything on agp: read references/llms.txt first

Start every agp task by opening [references/llms.txt](references/llms.txt) — a complete index of the live public docs (every page, one line + a `.md` URL). Find the page(s) for your task, fetch them, and work from those, not from memory. This file keeps no agp endpoint/param/field/limit/model detail on purpose: the docs are current, this file isn't.

Two anchors the index points into, worth calling out:
- **Exact shapes** (params, bodies, status codes, enums, limits) → the OpenAPI, authoritative and always current, unauthenticated: `https://agp.hcompany.ai/share/openapi.json` (rendered at `/share/docs`).
- **The `model` field** → the [Agents](https://hub.hcompany.ai/computer-use-agent/agents/overview.md) page. Non-obvious trap: the swagger types `model` as a free string and won't validate it, so a wrong id is accepted at create then fails at run — take the id from the docs, never from memory.

## Get a key into .env (the one thing the docs can't do for you)

```bash
python scripts/h_login.py            # desktop PKCE flow → writes HAI_API_KEY into ./.env; no-op if already set
python scripts/h_login.py --force    # rotate/replace; also --region us|eu (default eu), --env-file, --key-name, --no-rotate
```

Opens the browser (one Google click), exchanges the code, picks the org, writes `.env` (chmod 600). Headless fallback and full portal auth details: [references/portal/auth.md](references/portal/auth.md).

**The SDK reads the `HAI_API_KEY` *environment variable*, not the `.env` file.** A key freshly written to `.env` still gives `ApiError: ... setting HAI_API_KEY` until it's loaded into the environment (`source .env` or equivalent — and since each Bash call is a fresh shell, do it in the same command as the Python). Classic false alarm: the key is fine, it's just not exported.

## Using the hai-agents SDK

Prefer the SDK over hand-rolled HTTP — but **the SDK's shape is not the HTTP shape, so introspect the installed package instead of guessing.** Its module layout, the session handle's surface, and several field names diverge from the wire; guessing them is the single biggest source of crashes, and nothing I write here would stay accurate. One line settles it:

```bash
python3 -m venv .hai-venv && .hai-venv/bin/pip install -q hai-agents   # `pip` is often absent and system pythons are externally-managed (PEP 668); a venv sidesteps both
.hai-venv/bin/python -c "import hai_agents, inspect; print(dir(hai_agents)); print(inspect.signature(hai_agents.run_session))"   # dir()/signature() need no key
```

Pure `dir()`/`inspect.signature()` introspection needs no key, but the moment you instantiate a `Client()` or list the agent catalog you do — so load `.env` first (see above), or you'll waste round-trips chasing a phantom `HAI_API_KEY` error.

Package surfaces (versions, examples): [PyPI](https://pypi.org/project/hai-agents/) / [npm](https://www.npmjs.com/package/hai-agents). Both default to the EU endpoint — set `base_url` for US.

## The trap the docs won't warn you about

**The task goes in `messages`, never in `instructions`.** `instructions` is the system prompt — *who* the agent is and its guardrails; `messages` is *what to do now*. A session created with rich instructions but **no message** starts, immediately flips to `idle`, and does nothing — which reads like a dead platform but is just a missing message. (Easiest path: use a pre-built `h/` agent — the environment, model, and instructions are already wired and you only supply the message. But **never guess an agent id** — list the catalog first with `GET /api/v2/agents` (SDK: `client.agents.list_agents()`) and pick from the result; an invented `h/...` name just 404s.)

## Show the user the run — offer to open it

When a runnable script is ready, don't end with a prose "Want me to run it?" buried under a wall of explanation — put a **clean yes/no choice** in front of the user (an explicit prompt / choice, not an open question they have to answer in free text). The decision is theirs, but make saying yes a single tap.

**The instant they say yes, hand them the agent-view (replay) link.** Don't disappear into a long blocking run and surface the link at the end — surfacing it after the fact is the failure. Create the session, print the link, and offer to open it *first thing*, then let the run proceed (see ordering below).

The agent-view link is **deterministic from the session id**, which you have the instant you create the session — long before the run finishes. The whole point is to let the user watch **live**, so the link has to reach them *while the agent is still working*.

The trap that defeats this: `wait_for_session` / `run_session` **blocks for the entire run**, and you only see a command's stdout when it *returns*. So if you create the session and block inside **one foreground command**, the link doesn't surface until the run is already over — which is exactly the after-the-fact replay you're trying to avoid. The fix is structural: the create+link step must hand control back to you *before* the long wait begins. Two ways:

- **Background the run (preferred):** print the link **first, flushed** (`print(url, flush=True)`), start the script as a background task, read the link from its opening output and offer to open it — then let the task run and report the result when it completes.
- **Or split into two commands:** one fast command that creates the session and prints id + link then exits, then a second that resumes from that id and blocks on the wait.

Either way, build the URL yourself from the id (`https://<host>/agent-view/{id}`) — don't scrape it from stdout, and don't busy-loop `grep`-ing a log file for `agent-view/` (that just hangs).

**The host must match the region you called, and these APIs default to EU** — so the link is usually `https://platform.eu.hcompany.ai/agent-view/{id}`; only US sessions use `https://platform.hcompany.ai/agent-view/{id}`. Don't hand an EU session a bare `platform.hcompany.ai` link — it points at the wrong region's UI and the run won't be there.

Deeper UI/UX notes (deep-linking, sharing outside the org): [references/extras/agent-view-replay.md](references/extras/agent-view-replay.md).

## Something broken? Report it to support@hcompany.ai

If agp behaves differently than the docs say — unexplained 5xx, a session stuck with no events, a key rejected right after creation — write the report *for* the user: region + host, exact endpoint + method, full response (status, `detail`, headers like `ETag`/`Retry-After`), UTC timestamp, session id + agent-view link, expected vs observed, minimal repro. Never include `hk-` keys or tokens. Then offer a pre-filled `mailto:support@hcompany.ai` (or a draft via a connected mail tool) — the user hits Send, not you.
