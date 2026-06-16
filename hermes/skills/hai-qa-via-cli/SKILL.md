---
name: hai-qa-via-cli
description: >
  Run an autonomous QA review of a web UI by invoking the local `qa-cli` command via the shell.
  Trigger when the user asks to QA a URL, check a deployed site for accessibility, usability,
  or correctness issues, get a structured review of a page, or run a quick visual sanity check
  on a live page (e.g. "what color is the CTA?").
version: 1.0.0
metadata:
  hermes:
    tags: [web, qa, accessibility, browser-agent]
    category: web
---

# Web QA via the hai-agents CLI (Hermes Agent)

When the user asks you to QA a web UI, review a deployed page, or check a URL for issues:

## 1. Pick the right subcommand

- `qa-cli review`: full agent loop (about 30-90s). Returns a structured `ReviewResult` JSON with `verdict`, `summary`, `findings` (each with `severity`, `area`, `issue`, `suggestion`), and `steps_taken`. Use this for any real review.
- `qa-cli visual`: one-shot visual question, returns a short free-text answer. Use for quick "what color is X" or "does the layout look broken" sanity checks.

## 2. Invoke

The `qa-cli` command lives in the `hai-agent-demos` repo and must run against that project.
`uv run --directory` resolves it regardless of your current working directory. Point
`HAI_DEMOS` at your clone, or export it once in your shell to avoid editing this file:

```bash
HAI_DEMOS="${HAI_DEMOS:-/path/to/agent-sdk-demo}"   # exported HAI_DEMOS wins; else edit the fallback
uv run --directory "$HAI_DEMOS" --env-file "$HAI_DEMOS/.env" qa-cli review --url <url> --instruction "<what to focus on>"
uv run --directory "$HAI_DEMOS" --env-file "$HAI_DEMOS/.env" qa-cli visual --url <url> --question "<single question>"
```

The CLI logs progress to stderr; the result (JSON for `review`, text for `visual`) goes to stdout. Pipe to `jq` if you want to filter.

## 3. Surface the result

For `review`:

- Lead with the `verdict` and the headline `summary`.
- List `findings` ordered as returned (already high-severity-first). Show each as `[severity] area: issue` and include the suggestion when actionable.
- If `verdict == "fail"`, make it clear what blocked completion.

For `visual`: just relay the answer.

## Notes

- Prerequisite: the `qa-cli` command comes from the [`hai-agent-demos`](https://github.com/hcompai/hai-agent-demos) repo. If `uv run ... qa-cli` errors with "command not found" or a project-resolution error, the repo isn't at the `--directory` path. Tell the user to clone it and run `uv sync`, or fix the path, before retrying.
- Requires `HAI_API_KEY` in the repo's `.env` (passed via `--env-file` above). On a missing key the CLI exits with `error: HAI_API_KEY is not set...`. Relay that to the user verbatim; don't retry.
- `review` is expensive (one cloud session per call). Don't run multiple `review`s in parallel for the same task; call it once with a focused `--instruction`.
- The browser-agent intelligence runs in the H cloud, not in your model. You only launch the command and surface the JSON, so this works the same whichever model is driving Hermes.

## Examples

> **User:** "Please QA https://news.ycombinator.com for accessibility."
> **You:** Run `uv run --directory "$HAI_DEMOS" --env-file "$HAI_DEMOS/.env" qa-cli review --url https://news.ycombinator.com --instruction "focus on accessibility: alt text, form labels, keyboard nav, contrast"`. Parse JSON. Surface findings.

> **User:** "What color is the main CTA on https://example.com?"
> **You:** Run `uv run --directory "$HAI_DEMOS" --env-file "$HAI_DEMOS/.env" qa-cli visual --url https://example.com --question "what color is the main call-to-action button?"`. Return the answer.

## Install (Hermes Agent)

Copy this skill into Hermes' skills directory and reload:

```bash
mkdir -p ~/.hermes/skills/hai
cp -r <this-repo>/hermes/skills/hai-qa-via-cli ~/.hermes/skills/hai/hai-qa-via-cli
# then restart Hermes; it re-scans ~/.hermes/skills/ on startup
```
