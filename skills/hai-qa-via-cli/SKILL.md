---
name: hai-qa-via-cli
description: >
  Run an autonomous QA review of a web UI by invoking the local `qa-cli` command via Bash.
  Trigger when the user asks to QA a URL, check a deployed site for accessibility, usability,
  or correctness issues, get a structured review of a page, or run a quick visual sanity check
  on a live page (e.g. "what color is the CTA?").
---

# Web QA via the hai-agents CLI

When the user asks you to QA a web UI / review a deployed page / check a URL for issues:

## 1. Pick the right subcommand

- **`qa-cli review`** — full agent loop (~30–90s). Returns a structured `ReviewResult` JSON with `verdict`, `summary`, `findings` (each with `severity`, `area`, `issue`, `suggestion`), and `steps_taken`. Use this for any real review.
- **`qa-cli visual`** — one-shot visual question, returns a short free-text answer. Use for quick "what color is X" / "does the layout look broken" sanity checks.

## 2. Invoke

```bash
uv run qa-cli review --url <url> --instruction "<what to focus on>"
uv run qa-cli visual --url <url> --question "<single question>"
```

The CLI logs progress to stderr; the result (JSON for `review`, text for `visual`) goes to stdout. Pipe to `jq` if you want to filter.

## 3. Surface the result

For `review`:

- Lead with the `verdict` and the headline `summary`.
- List `findings` ordered as returned (already high-severity-first). Show each as `[severity] area — issue` and include the suggestion when actionable.
- If `verdict == "fail"`, make it clear what blocked completion.

For `visual`: just relay the answer.

## Notes

- **Prerequisite**: the `qa-cli` command comes from the [`hai-agents-demos`](https://github.com/hcompai/hai-agents-demos) repo. If `uv run qa-cli ...` errors with "command not found", that repo isn't installed in the current working directory — tell the user to clone it and run `uv sync` before retrying, or fall back to whichever QA tool is already on PATH.
- Requires `HAI_API_KEY` in `.env`. On a missing key the CLI exits with `error: HAI_API_KEY is not set...` — relay that to the user verbatim; don't retry.
- `review` is expensive (one cloud session per call). Don't run multiple `review`s in parallel for the same task — call it once with a focused `--instruction`.

## Examples

> **User:** "Please QA https://news.ycombinator.com for accessibility."
> **You:** Run `uv run qa-cli review --url https://news.ycombinator.com --instruction "focus on accessibility — alt text, form labels, keyboard nav, contrast"`. Parse JSON. Surface findings.

> **User:** "What color is the main CTA on https://example.com?"
> **You:** Run `uv run qa-cli visual --url https://example.com --question "what color is the main call-to-action button?"`. Return the answer.
