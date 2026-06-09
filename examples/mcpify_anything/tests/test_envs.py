"""Tests for the shared ``browser_env`` helper."""

from examples._shared import browser_env


def test_browser_env_omits_mode() -> None:
    # Regression lock: mode must stay unset so the server applies its own default.
    env = browser_env("https://example.test")
    assert env.mode is None
    assert "mode" not in env.model_dump(exclude_none=True)


def test_browser_env_core_fields() -> None:
    env = browser_env("https://example.test")
    assert env.kind == "web"
    assert env.headless is True
    assert env.start_url == "https://example.test"
    assert env.width > 0 and env.height > 0
