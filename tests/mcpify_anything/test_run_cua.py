"""Tests for ``CuaRunner.run`` — SDK wiring, errors, timeouts, logging."""

import logging
from types import SimpleNamespace
from typing import Any

import pytest
from hai_agents import AsyncClient, Browser, SessionRunResult, TrajectoryChanges
from hai_agents.core import ApiError
from pydantic import BaseModel

from examples.mcpify_anything.runner import CuaError, CuaRunner, RunSpec

_BASE_URL = "https://agp.test"
_TEST_ARTIFACT = "test-artifact"


class _Out(BaseModel):
    value: int


def _env() -> list[Browser | str]:
    return [Browser(id="browser", headless=True, width=800, height=600, start_url="https://x.test")]


def _runner(client: AsyncClient, agent_artifact: str) -> CuaRunner:
    return CuaRunner(client, _BASE_URL, agent_artifact)


def _spec() -> RunSpec[_Out]:
    return RunSpec(
        task="t",
        output_model=_Out,
        environments=_env(),
        instructions="i",
        max_steps=3,
        max_time_s=5.0,
    )


def _patch_create(monkeypatch: pytest.MonkeyPatch, client: AsyncClient, capture: dict[str, Any] | None = None) -> None:
    async def fake_create(
        *,
        agent: Any,
        messages: Any = None,
        max_steps: int | None = None,
        max_time_s: float | None = None,
        idle_timeout_s: int | None = None,
        agent_artifact: str | None = None,
        **_kwargs: Any,
    ) -> Any:
        if capture is not None:
            capture["agent"] = agent
            capture["idle_timeout_s"] = idle_timeout_s
            capture["agent_artifact"] = agent_artifact
        return SimpleNamespace(id="sess-test")

    monkeypatch.setattr(client.sessions, "create_session", fake_create)


def _patch_wait(monkeypatch: pytest.MonkeyPatch, result: SessionRunResult) -> None:
    async def fake_wait(_client: AsyncClient, _session_id: str, **_kwargs: Any) -> SessionRunResult:
        return result

    monkeypatch.setattr("examples.mcpify_anything.runner.async_wait_for_session", fake_wait)


def _patch_wait_raising(monkeypatch: pytest.MonkeyPatch, exc: BaseException) -> None:
    async def fake_wait(*_args: Any, **_kwargs: Any) -> SessionRunResult:
        raise exc

    monkeypatch.setattr("examples.mcpify_anything.runner.async_wait_for_session", fake_wait)


def _completed_with(answer: dict[str, Any] | None) -> SessionRunResult:
    return SessionRunResult(
        id="sess-test",
        status="completed",
        events=[],
        next_from_index=0,
        final_changes=TrajectoryChanges(status="completed", answer=answer),
    )


def _terminal_without_answer(status: str) -> SessionRunResult:
    return SessionRunResult(
        id="sess-test",
        status=status,
        events=[],
        next_from_index=0,
        final_changes=TrajectoryChanges(status=status),
    )


async def test_sets_answer_format_and_validates(monkeypatch: pytest.MonkeyPatch, client: AsyncClient) -> None:
    capture: dict[str, Any] = {}
    _patch_create(monkeypatch, client, capture)
    _patch_wait(monkeypatch, _completed_with({"value": 7}))

    result = await _runner(client, _TEST_ARTIFACT).run(_spec())

    assert result == _Out(value=7)
    assert capture["agent"].answer_format == _Out.model_json_schema()  # carried by the inline Agent since SDK 0.1.6
    assert capture["idle_timeout_s"] is None  # one-shot: session ends when the agent answers


async def test_forwards_agent_artifact(monkeypatch: pytest.MonkeyPatch, client: AsyncClient) -> None:
    # Without this, AGP falls back to its default and our agent build never runs.
    capture: dict[str, Any] = {}
    _patch_create(monkeypatch, client, capture)
    _patch_wait(monkeypatch, _completed_with({"value": 1}))

    await CuaRunner(client, _BASE_URL, "mcpify-anything-agent").run(_spec())

    assert capture["agent_artifact"] == "mcpify-anything-agent"


async def test_session_creation_failure_raises_cua_error(monkeypatch: pytest.MonkeyPatch, client: AsyncClient) -> None:
    async def fake_create(**_kwargs: Any) -> Any:
        raise ApiError(status_code=500, body="platform refused")

    monkeypatch.setattr(client.sessions, "create_session", fake_create)
    with pytest.raises(CuaError, match="session creation failed"):
        await _runner(client, _TEST_ARTIFACT).run(_spec())


async def test_failed_status_without_answer_raises(monkeypatch: pytest.MonkeyPatch, client: AsyncClient) -> None:
    _patch_create(monkeypatch, client)
    _patch_wait(monkeypatch, _terminal_without_answer("failed"))
    with pytest.raises(CuaError, match="without a structured answer"):
        await _runner(client, _TEST_ARTIFACT).run(_spec())


async def test_completed_without_any_answer_raises(monkeypatch: pytest.MonkeyPatch, client: AsyncClient) -> None:
    _patch_create(monkeypatch, client)
    _patch_wait(monkeypatch, _terminal_without_answer("completed"))
    with pytest.raises(CuaError, match="without a structured answer"):
        await _runner(client, _TEST_ARTIFACT).run(_spec())


async def test_bad_schema_raises(monkeypatch: pytest.MonkeyPatch, client: AsyncClient) -> None:
    _patch_create(monkeypatch, client)
    _patch_wait(monkeypatch, _completed_with({"wrong": "field"}))
    with pytest.raises(CuaError, match="answer did not match"):
        await _runner(client, _TEST_ARTIFACT).run(_spec())


async def test_timeout_propagates(monkeypatch: pytest.MonkeyPatch, client: AsyncClient) -> None:
    # Not wrapped in CuaError on purpose — TimeoutError is clearer on its own.
    _patch_create(monkeypatch, client)
    _patch_wait_raising(monkeypatch, TimeoutError("session did not finish"))
    with pytest.raises(TimeoutError):
        await _runner(client, _TEST_ARTIFACT).run(_spec())


async def test_logs_agent_view_link_on_every_session(
    monkeypatch: pytest.MonkeyPatch, client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    # The link is how a developer recovers a trajectory after a failed run.
    _patch_create(monkeypatch, client)
    _patch_wait(monkeypatch, _completed_with({"value": 7}))

    with caplog.at_level(logging.INFO, logger="examples.mcpify_anything.runner"):
        await _runner(client, _TEST_ARTIFACT).run(_spec())

    assert "agent view:" in caplog.text
    assert "agent-view/sess-test" in caplog.text
