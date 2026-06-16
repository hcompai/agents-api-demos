<!--
Thanks for contributing to hai-agents-demos. Please read AGENTS.md for the
coding conventions this repo enforces (Ruff line length 120, tyro CLIs,
Pydantic `.make()` configs, file-structure ordering, etc.).
-->

## Summary

<!-- What does this PR do, and why? One or two sentences. -->

## Type of change

- [ ] New example / recipe
- [ ] New skill
- [ ] Fix to an existing example or skill
- [ ] Docs / README
- [ ] Tooling / CI / repo plumbing

## Related issues

<!-- e.g. "Closes #123", or "N/A" if none. -->

## What changed

<!-- Bullet the notable changes. Mention any new tools, CLI subcommands, or skills added. -->

-

## How was this tested?

<!--
Show it works. For example:
- `ruff check .` and `ruff format --check .` pass
- `mypy` passes
- `pytest <path>` passes
- Manual run: the exact `uv run ...` command or Claude Code prompt you used, and what you saw
-->

## Checklist

- [ ] I read [AGENTS.md](../AGENTS.md) and followed the code style.
- [ ] `ruff check .`, `ruff format .`, and `mypy` pass locally (`pre-commit run --all-files`).
- [ ] New examples/skills are documented in the README table and project layout.
- [ ] New skills are registered in `.claude-plugin/marketplace.json`.
- [ ] No secrets (`HAI_API_KEY`, `.env` contents) are included in the diff.
