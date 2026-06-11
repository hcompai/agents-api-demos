# Reviewing agent runs in the browser (agent-view)

Every agent platform session/trajectory can be watched and replayed step-by-step in a browser — screenshots, events, agent reasoning. This is how a human inspects what the agent actually did.

## The reflex to build

**Whenever you create, run, or debug a session for the user, give them the agent-view link — and offer to open it in their browser.** They will almost always want to *watch* the run, not just read your summary of it:

```
https://platform.hcompany.ai/agent-view/{session_id}
```

Concretely:

- **When you start working against the platform** (first session of a task), offer once to open the platform UI (`open "https://platform.eu.hcompany.ai"` — or the US host) so the user has it at hand.
- **The moment each run launches**, ask the user if they want it opened in their browser ("want me to open the run?") — and on yes:

```bash
open "https://platform.eu.hcompany.ai/agent-view/{session_id}"   # macOS; xdg-open on Linux
```

- If they said yes once and you launch several runs in the same task, keep opening them (or open the first and link the rest) — don't re-ask every time.
- Always print the link in your answer too, even when you opened the tab — it's what survives in the transcript.

The `{session_id}` is the id returned by `POST /api/v2/sessions` (the v2 session id and the trajectory id are the same UUID).

**Match the region of the link to the region of the API you called**: a session created on `agp.eu.hcompany.ai` is viewable at `platform.eu.hcompany.ai`, not on the US host. Remember the hai-agents SDK defaults to EU — if the user ran through the SDK with defaults, the EU link is probably the right one.

| API host used | agent-view link |
|---|---|
| `agp.hcompany.ai` (US) | `https://platform.hcompany.ai/agent-view/{id}` |
| `agp.eu.hcompany.ai` (EU) | `https://platform.eu.hcompany.ai/agent-view/{id}` |
| `agp.<env>.sandboxh.ai` (staging/dev) | `https://platform.<env>.hcompany.ai/agent-view/{id}` |

## Jumping to a specific moment

Query params let you deep-link into the run — useful when reporting a finding ("the agent mis-clicked at step 12"):

```
https://platform.hcompany.ai/agent-view/{id}?event=12&expanded=true&screenshot=12
```

- `event=N` — open at event N
- `expanded=true` — expand the event detail
- `screenshot=N` — show the screenshot at that step

## Live vs replay

Same URL for both: while the session runs, the view follows it live; once it finishes, the same link serves as the replay. (Separately, a `LiveViewUrlEvent` may appear in the event stream with an embedded live-browser URL — that is a transient in-run view, not the durable review link. Always hand the user the agent-view link.)

## Who can open it, and sharing

- A **logged-in platform user of the same org** can open the link directly — no sharing step needed.
- To show the run to someone **outside the org** (or unauthenticated), make it public first: `POST /api/v2/sessions/{id}/share` → returns a public share path; `DELETE .../share` revokes it. Shapes and ownership rules: [../agp/sessions.md](../agp/sessions.md) (§ share routes).
