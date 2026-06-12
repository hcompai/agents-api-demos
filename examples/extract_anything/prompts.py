"""Operator instructions for the extract_anything agent, loaded from ``prompts/`` at import time."""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent / "prompts"

OPERATOR_INSTRUCTIONS = (_PROMPTS_DIR / "extractor_instructions.md").read_text()
