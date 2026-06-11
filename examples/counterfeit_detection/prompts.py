"""Loader for the three counterfeit-detection stages' instruction strings.

Each per-stage ``.md`` file in ``prompts/`` carries only that stage's addendum; ``ground_rules.md`` is
the shared persona + rules that prefixes all three. Tasks (the ``messages`` parameter) stay as Python
constants here because they are short ``.format(genuine_url=...)`` interpolators, not prose blocks.
"""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_GROUND_RULES = (_PROMPTS_DIR / "ground_rules.md").read_text()

SIMPLE_INSTRUCTIONS = _GROUND_RULES + (_PROMPTS_DIR / "simple.md").read_text()
TOOLED_INSTRUCTIONS = _GROUND_RULES + (_PROMPTS_DIR / "tooled.md").read_text()
SWEEP_INSTRUCTIONS = _GROUND_RULES + (_PROMPTS_DIR / "sweep.md").read_text()

SIMPLE_TASK = "Find one counterfeit listing of the genuine product at {genuine_url}."

SWEEP_TASK = (
    "Find as many distinct counterfeit listings as you can of the genuine product at {genuine_url}. "
    "Record each confirmed one with record_counterfeit and keep going until your budget runs out."
)
