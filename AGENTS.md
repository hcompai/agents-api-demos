# AGENTS.md — hai-agent-demos

## Working with Users

- **Clarify first**: when requirements are ambiguous or under-specified, ask the user for clarifications before establishing a plan or writing code.

## Development Setup

- **uv** for package management (required version ≥0.9.18)
  - `uv sync` — sync dependencies
  - **Never use `pip` directly** — always use `uv` commands; if you must install a package ad-hoc, use `uv pip install`
- Copy `.env.example` to `.env` and configure
- **Never read `.env`** — it contains credentials; if a value needs to be set or changed, instruct the user to edit `.env` directly

## Code Style

### General

- **Formatter**: Ruff, line length **120**, Google-style docstrings (non-default)
- **Modularity**: keep functions short and single-purpose; use guard clauses at the top to handle edge cases early; split complex logic into well-named helpers
- **Naming**: use explicit, descriptive names; follow standard Python casing — `snake_case` for variables/functions, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants
- **Imports**: keep all imports at the top of the file; only use lazy (inline) imports when there is a clear performance reason (e.g., heavy dependency in a rarely-used code path)
- **Collections for constants**: use tuples for fixed-structure literals that won't be mutated (e.g., pairs iterated together: `((source_a, dest_a), (source_b, dest_b))`). Reserve lists for collections that are actually mutated or semantically variable-length. Tuples signal immutability to the reader and are marginally faster to iterate.
- **Error handling**: no unnecessary `try`/`except` blocks; merge adjacent `try`/`except` blocks in the same function unless they genuinely recover differently. Back-to-back cleanup `except`s that all just log-and-continue (or all just `pass`) should be a single block — separate handlers imply different recovery, so the structure should match the intent.

### Comments & docstrings

- **Comments**: only comment genuinely non-obvious logic — well-named, modular code should not need them
- **Docstrings**: public functions and `__init__` methods need a Google-style `Args:` section (plus `Returns:` / `Raises:` when relevant). A class-level docstring does not substitute for an `__init__` `Args:` block. Trivial private helpers can skip it when the signature is self-explanatory.

### Classes & file structure

- **Classes**: only use classes when truly relevant — prefer plain functions for stateless logic; no attribute-less classes; prefer module-level functions over methods that don't use `self`
- **Private placement**: class methods prefixed `_` go at the **end** of the class; module-level private classes/functions go **after** all public ones (see file structure below)
- **File structure**: enforce this top-to-bottom order in every Python file:
  1. Module docstring
  2. Imports (stdlib → third-party → local)
  3. Constants
  4. Public classes
  5. Public functions
  6. Private classes
  7. Private functions
  8. `main` (if applicable) — placed immediately above the `if __name__ == "__main__":` block so the entry point sits next to its invocation
  9. `if __name__ == "__main__":` (if applicable)

### Pydantic configs

When a runtime class takes non-trivial configuration — a tyro CLI, many fields, or sub-configs to compose — pair it with a Pydantic config and a `.make()` factory:

```python
class MyClassConfig(BaseModel):
    name: str
    """Display name used in logs."""
    sub_config: SomeOtherConfig | None = None
    """Optional helper config; when set, builds MyClass.helper."""

    def make(self) -> MyClass:
        return MyClass(self)

class MyClass:
    def __init__(self, config: MyClassConfig):
        self.config = config
        self.helper = config.sub_config.make() if config.sub_config else None
```

- **Single `config` arg**: `__init__` takes only `config: MyClassConfig` and stores it as `self.config` — do not unwrap fields into separate `__init__` args.
- **Defaults live on the config**: all argument definitions and defaults go on the `BaseModel`, never on `__init__`.
- **Sub-configs via `.make()`**: in `__init__`, call `.make()` on each sub-config and attach the result as an attribute.
- **`make` signature**: always `def make(self) -> MyClass: return MyClass(self)`.
- **Field docstrings**: triple-quoted strings under each field (shown above), not `# inline comments`.
- **Skip the pattern for small classes**: if the class has only 1–2 parameters, no tyro CLI, and no sub-configs, pass the parameters directly to `__init__`. A config whose fields get unpacked at the call site adds indirection without value.

### CLI scripts

- **Parsers**: `tyro` is preferred over `click`; never use `argparse`
- **Two valid shapes**:
  - **Function-based** (preferred for short demo CLIs) — pass plain functions to `tyro.extras.subcommand_cli_from_dict({"name": fn, ...})`. Each subcommand is one top-level function; tyro derives the parser from its signature and docstring. Used by every CLI in this repo.
  - **Pydantic-config** (use when a CLI has many options, sub-configs, or composes with non-CLI callers) — define a `BaseModel` config, parse with `tyro.cli(Config)`, hand the config to the runtime class via `.make()`. File order in that case: module docstring → config model → `tyro.cli()` → `logging` setup.
- **Output**: use `logging` for operational messages and `print` only to display results to the user

## Useful Commands

| Task          | Command                      |
| ------------- | ---------------------------- |
| Sync deps     | `uv sync`                    |
| Lint check    | `ruff check .`               |
| Lint fix      | `ruff check --fix .`         |
| Format        | `ruff format .`              |
| Type check    | `mypy`                       |
| Run tests     | `pytest <path>`              |
| Pre-commit    | `pre-commit run --all-files` |
