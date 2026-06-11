# hai-agents — TypeScript SDK

One-line summary: how to use the published `hai-agents` npm package (Fern-generated client + handwritten polling overlay, source: github.com/hcompai/hai-agents-ts) to launch, stream, steer, and manage Agent Platform v2 sessions — instead of hand-rolling HTTP against [../agp/](../agp/conventions-and-sdk.md).

## Table of contents

1. [Install & auth](#1-install--auth)
2. [High-level helpers: runSession, startSession, SessionHandle](#2-high-level-helpers)
3. [The generated client surface → v2 routes](#3-generated-client-surface)
4. [Events & how polling works](#4-events--how-polling-works)
5. [Errors](#5-errors)
6. [Gotchas](#6-gotchas)
7. [Always hand back the replay link](#7-always-hand-back-the-replay-link)

---

## 1. Install & auth

```bash
npm install hai-agents     # Node >= 18 (needs global fetch); ships ESM + CJS builds ("type": "module", dist/index.js + dist/index.cjs)
export H_API_KEY=hk-...    # create at https://platform.hcompany.ai (see ../portal/api-keys.md for the automated flow)
```

```ts
import { HaiAgentsClient, HaiAgentsEnvironment } from "hai-agents";

const client = new HaiAgentsClient();                       // apiKey ?? process.env.H_API_KEY; environment defaults to EU
const usClient = new HaiAgentsClient({
  apiKey: "hk-...",                                          // explicit key beats the env var
  environment: HaiAgentsEnvironment.Us,                      // "https://agp.hcompany.ai"; Eu = "https://agp.eu.hcompany.ai" (DEFAULT)
});
```

Other `HaiAgentsClient.Options` (= `BaseClientOptions`): `baseUrl` (raw URL override, beats `environment`), `headers`, `timeoutInSeconds` (default 60 per request), `maxRetries` (default 2, retried on 408/429/5xx honoring `Retry-After`), `fetch` (custom impl), `logging`, `auth` (advanced: `false`, an `AuthProvider`, or a header-returning function). A missing key only fails at call time with `HaiAgentsError`: "Please provide 'apiKey' when initializing the client, or set the 'H_API_KEY' environment variable".

## 2. High-level helpers

The public `HaiAgentsClient` extends the generated Fern client with three handwritten conveniences (also exported as standalone functions `runSession(client, opts)` / `waitForSession(client, opts)`):

- `client.runSession(options): Promise<SessionRunResult>` — create + block until terminal status.
- `client.startSession(params): Promise<SessionHandle>` — create, return a handle immediately.
- `client.session(id): SessionHandle` — wrap an existing session id (no HTTP call).

Options are **flat** `SessionRequest` fields plus `idempotencyKey` (`CreateSessionParams`), and for `runSession` also the wait knobs `waitForSeconds` (long-poll, default 20), `includeEvents` (default true), `timeoutMs` (wall-clock budget, throws when exceeded), `pollBackoffMs`, `maxPolls`.

```ts
type SessionRunResult = {
  id: string;
  status: TrajectoryStatus;          // terminal: "completed" | "failed" | "timed_out" | "interrupted"
  events: TrajectoryEvent[];         // accumulated stream (empty if includeEvents: false)
  nextFromIndex: number;             // resume cursor for further getSessionChanges calls
  finalChanges?: TrajectoryChanges;
  answer?: string | Record<string, unknown>;   // shortcut for finalChanges.answer; object when the agent has an answerFormat
};
```

### Example 1 — launch a web agent with an inline agent spec, block for the answer

```ts
import { HaiAgentsClient } from "hai-agents";

const client = new HaiAgentsClient();
const result = await client.runSession({
  agent: {                                   // SessionRequestAgent = string | Agent (inline definition)
    name: "price-checker",
    description: "Looks up product prices on the web",
    // AgentEnvironmentsItem = string (registered environment id) | inline Environment (a Browser: id required;
    // kind "web"; optional headless, width/height, startUrl, mode "visual"|"multimodal"|"text", pageChars)
    environments: [{ id: "price-checker-browser", kind: "web", startUrl: "https://www.google.com" }],
  },
  messages: "Find the price of the Framework Laptop 16 base config",
  maxSteps: 40,
  timeoutMs: 10 * 60 * 1000,
});
console.log(result.status, result.answer);
```

### Example 2 — run a stored agent by name (the common case)

```ts
const result = await client.runSession({
  agent: "h/web-surfer-holo3-1-35b",       // registered agent name; list with client.agents.listAgents()
  messages: "What are the top 3 stories on Hacker News right now?",
  idempotencyKey: "hn-top3-2026-06-10",    // safe retries; sent as the Idempotency-Key header
});
```

### Example 3 — interact mid-run with a SessionHandle

```ts
const handle = await client.startSession({
  agent: "h/web-surfer-holo3-1-35b",
  messages: "Compare iPhone 17 prices on two retailer sites",
  idleTimeoutS: 120,                                       // keep the session open for follow-ups after each answer
});
console.log(`watch live: https://platform.eu.hcompany.ai/agent-view/${handle.id}`);

await handle.sendMessage({ type: "user_message", message: "Only consider EU stores" });
const { status, steps } = await handle.status();           // cheap snapshot
const result = await handle.waitForCompletion();           // same loop/options as waitForSession
```

`SessionHandle` methods → HTTP: `get()` (`GET /sessions/{id}`), `status()`, `changes(opts?)`, `sendMessage(body)` (`POST /sessions/{id}/messages`, body is `{type:"user_message", message, images?}` or `{type:"batch", messages:[...]}`), `pause()` / `resume()`, `cancel()` (`DELETE /sessions/{id}`), `forceAnswer()`, `waitForCompletion(opts?)`. There is no EventEmitter/async-iterator surface — streaming = the long-poll loop in `waitForSession`; for manual streaming, loop `getSessionChanges` yourself advancing `fromIndex` (see §4).

## 3. Generated client surface

Five lazily-created resource clients; method names match v2 route function names (camelCased — full route semantics in [../agp/sessions.md](../agp/sessions.md) and friends):

| Resource | Methods |
|---|---|
| `client.sessions` | `listSessions`, `createSession({ idempotencyKey?, body })`, `getSessionQuota`, `getSession`, `cancelSession`, `getSessionStatus`, `sendSessionMessages`, `pauseSession`, `resumeSession`, `forceSessionAnswer`, `getSessionChanges`, `listSessionEvents`, `submitSessionFeedback`, `submitEventFeedback`, `shareSession`, `unshareSession`, `getSessionResource` |
| `client.agents` | `listAgents`, `createAgent`, `getAgent`, `updateAgent`, `deleteAgent` |
| `client.skills` | `listSkills`, `createSkill`, `getSkill`, `updateSkill`, `deleteSkill` |
| `client.environments` | `listEnvironments`, `createEnvironment`, `getEnvironment`, `updateEnvironment`, `deleteEnvironment` |
| `client.vaults` | `listVaults`, `createVault`, `getVault`, `updateVault`, `deleteVault`, `rotateVaultToken`, `vaultHealth` |

- **Note the nesting**: the raw `createSession` takes `{ idempotencyKey?, body: SessionRequest }`; only the high-level `runSession`/`startSession` take flat fields.
- **Pagination** is page-number based, not cursor based: list requests take `page` (1-based) and `size`; responses are `Page*` objects `{ items, total, page }` (e.g. `PageAgent`, `PageSessionSummary`). `listSessions` also filters by `owner` (`"me" | "me-in-organization" | "organization" | "me-or-organization"`), `status`, `agent`, `groupId`, `parentSessionId`, `search`, `createdBefore/After`, `finishedBefore/After`, `sort` (`"created_at" | "-created_at"`).
- **Request-size guard**: `runSession`/`startSession` run `assertRequestUnderLimit(params)` — throws a plain `Error` ("Request payload is X MB, over the 5.00MB limit. Downscale images before sending.") before any HTTP if the JSON body exceeds `MAX_REQUEST_BYTES` (5 MiB). The server enforces the same limit; raw `createSession` does not pre-check.
- Every method returns `core.HttpResponsePromise<T>` — `await` it like a normal promise, or `.withRawResponse()` to also get headers/status. Per-call `requestOptions`: `timeoutInSeconds`, `maxRetries`, `abortSignal`, extra `headers`/`queryParams`.
- **Escape hatch**: `client.fetch(input, init?, requestOptions?)` makes a passthrough request with the SDK's auth/retries/base URL — for endpoints not yet in the SDK.

## 4. Events & how polling works

Event/changes shapes (all camelCase in TS; the wire format is snake_case — serialization is handled for you, including `Date` parsing):

```ts
interface TrajectoryEvent { type: string; data?: unknown; timestamp: Date }
// common types: AgentStartedEvent, AgentCompletionEvent, AgentErrorEvent,
// AgentEvent (wraps policy_event / tool_result / observation_event), LiveViewUrlEvent, ChatMessageEvent

interface TrajectoryChanges {
  status: TrajectoryStatus;            // "pending"|"running"|"paused"|"idle"|"completed"|"failed"|"timed_out"|"interrupted"
  startedAt?: Date | null; finishedAt?: Date | null; error?: string | null;
  newEvents?: TrajectoryEvent[];
  answer?: string | Record<string, unknown> | null;
  metrics?: Metrics;
}
```

What `waitForSession` does for you (per loop iteration):

1. `getSessionChanges({ id, fromIndex, includeEvents: true, waitForSeconds })` — server long-polls; **a 204 (no new events) resolves to `undefined`**, no error. On 200, it appends `newEvents` and advances `fromIndex += newEvents.length` (that's the cursor — an event index, not a token).
2. `getSessionStatus({ id })` — the **authoritative** terminal check. `/changes` 204s even after the session finished, so status is what ends the loop (`isTerminalSessionStatus` / `TERMINAL_SESSION_STATUSES` are exported).
3. On terminal status, if the streamed changes never carried the answer, one final `getSessionChanges({ fromIndex: 0, includeEvents: false, waitForSeconds: 0 })` fetches it.

Replicate exactly that if you poll manually. For paginated history after the fact use `listSessionEvents` (`/changes` is for live tailing).

## 5. Errors

All exported from the package root:

| Error | When |
|---|---|
| `HaiAgentsError` | Base class. Any non-OK status without a dedicated class — e.g. **401** bad/missing key at the gateway, 403 writes to reserved `h/` resources, 404, **409** idempotent request still in flight (`Retry-After: 2` — the SDK's retry layer does NOT auto-retry 409, only 408/429/5xx), 429 concurrency quota. Fields: `.statusCode`, `.body`, `.rawResponse`, `.cause`. Also thrown (no statusCode) when no API key was resolvable. |
| `HaiAgents.UnprocessableEntityError` (extends `HaiAgentsError`) | **422** — validation errors (`.body` is `HttpValidationError` with `detail[].loc/msg/type`), blank/oversized `Idempotency-Key`, key reused with a different body (`IdempotencyKeyConflict`), invalid `overrides` path/type. |
| `HaiAgentsTimeoutError` | The HTTP request itself exceeded `timeoutInSeconds` (default 60). Distinct from… |
| plain `Error` | …`waitForSession` budget exhaustion ("Session {id} did not reach a terminal status within {timeoutMs}ms" / "before maxPolls=N") and the 5 MiB request-size guard. |

A session that *fails* is not an exception: `runSession` resolves with `status: "failed"` and `finalChanges.error` — always check `result.status`.

## 6. Gotchas

- **EU is the default environment** (`HaiAgentsEnvironment.Eu`, `https://agp.eu.hcompany.ai`) — it's listed first in the OpenAPI servers. Pass `environment: HaiAgentsEnvironment.Us` for the US region; API keys/sessions are region-scoped.
- The repo README's quickstart shows `runSession(client, { body: { agent, messages } })` — **stale**: per the source (`packages/sdk/src/client/polling.ts`, v0.1.5), `runSession`/`startSession` take **flat** fields (`{ agent, messages, ... }`); only the raw `client.sessions.createSession` nests under `body`.
- `apiKey` falls back to `process.env.H_API_KEY` lazily — constructor never throws; the first request does.
- Node >= 18 (relies on built-in `fetch`; injectable via the `fetch` option for other runtimes). Dual ESM/CJS package, zero runtime dependencies.
- Two classes named `HaiAgentsClient` exist in the source (`Client.ts` generated, `oo.ts` public subclass); the package root exports the **`oo.ts`** one with `runSession`/`startSession`/`session`. The `HaiAgents` namespace export carries all the request/response types (`HaiAgents.SessionRequest`, `HaiAgents.Agent`, …).
- `messages` accepts a plain string, one `UserMessageEvent`, or an array of them; images go in `UserMessageEvent.images` as base64 data URIs (mind the 5 MiB body limit).
- Response parsing is lenient (`skipValidation`, unknown keys pass through) — new server fields won't break old SDK versions.

## 7. Always hand back the replay link

After launching a session via the SDK, give the user the agent-view replay link — match the region to the client's environment (remember: **EU by default**):

```
https://platform.eu.hcompany.ai/agent-view/{session_id}   # HaiAgentsEnvironment.Eu (default)
https://platform.hcompany.ai/agent-view/{session_id}      # HaiAgentsEnvironment.Us
```

`{session_id}` is `result.id` / `handle.id` / `session.id`. Details (sharing, live view, what the page shows): [../extras/agent-view-replay.md](../extras/agent-view-replay.md).
