"""Tests for the dynamic-schema escape-hatch tool ``extract``."""

from collections.abc import Callable
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from pydantic import BaseModel

from examples.mcpify_anything.server import build_server
from tests.mcpify_anything._fakes import FakeRunner
from examples.mcpify_anything.tools.extract import ExtractInput, extract

_RECIPE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "calories_per_serving": {"type": "integer"},
        "summary": {"type": "string"},
    },
    "required": ["calories_per_serving", "summary"],
}


def _runner_returning(
    payload: dict[str, Any],
    schema: dict[str, Any],
    make_fake_runner: Callable[[BaseModel], FakeRunner],
) -> FakeRunner:
    # The framework builds the per-call answer model from ``args.answer_schema``; we mirror
    # that build here so the fixture's stored value is the right RootModel instance.
    args = ExtractInput.model_validate(
        {
            "site": "https://recipes.test/lasagna",
            "task": "read calories per serving",
            "answer_schema": schema,
        }
    )
    factory = extract.answer_model_factory
    assert factory is not None, "extract must be registered with an answer_model_factory"
    answer_model = factory(args)
    return make_fake_runner(answer_model.model_validate(payload))


async def test_extract_routes_caller_schema_into_runspec_answer_format(
    make_fake_runner: Callable[[BaseModel], FakeRunner],
) -> None:
    runner = _runner_returning({"calories_per_serving": 400, "summary": "lasagna"}, _RECIPE_SCHEMA, make_fake_runner)
    mcp = build_server(runner)

    async with Client(mcp) as c:
        await c.call_tool(
            "extract",
            {
                "args": {
                    "site": "https://recipes.test/lasagna",
                    "task": "Read the recipe page; report calories per serving.",
                    "answer_schema": _RECIPE_SCHEMA,
                }
            },
        )

    spec = runner.last_spec
    assert spec is not None
    rendered = spec.output_model.model_json_schema()
    # Caller's schema reaches the platform via ``answer_format``, under an identifier-safe title.
    assert rendered["required"] == _RECIPE_SCHEMA["required"]
    assert rendered["properties"] == _RECIPE_SCHEMA["properties"]
    assert rendered["title"] == "ExtractAnswer"
    assert rendered["title"].isidentifier()
    # The natural-language task is preserved verbatim in the prompt body.
    assert "Read the recipe page" in spec.task


async def test_extract_handler_receives_plain_dict_and_returns_it(
    make_fake_runner: Callable[[BaseModel], FakeRunner],
) -> None:
    payload = {"calories_per_serving": 510, "summary": "veg lasagna"}
    runner = _runner_returning(payload, _RECIPE_SCHEMA, make_fake_runner)
    mcp = build_server(runner)

    async with Client(mcp) as c:
        result = await c.call_tool(
            "extract",
            {
                "args": {
                    "site": "https://recipes.test/lasagna",
                    "task": "read calories",
                    "answer_schema": _RECIPE_SCHEMA,
                }
            },
        )

    # MCP serialises the dict; the client deserialises into a generic structured-content
    # object, but the underlying values must round-trip.
    assert dict(result.data) == payload


async def test_extract_falls_back_to_raw_schema_for_unrenderable_shapes(
    make_fake_runner: Callable[[BaseModel], FakeRunner],
) -> None:
    # ``schema_hint`` renders only a subset of JSON Schema. A valid caller schema outside that
    # subset (here: ``oneOf``) must not crash the tool call — the raw schema is embedded instead.
    oneof_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"value": {"oneOf": [{"type": "string"}, {"type": "integer"}]}},
        "required": ["value"],
    }
    runner = _runner_returning({"value": 3}, oneof_schema, make_fake_runner)
    mcp = build_server(runner)

    async with Client(mcp) as c:
        result = await c.call_tool(
            "extract",
            {
                "args": {
                    "site": "https://recipes.test/lasagna",
                    "task": "read the value",
                    "answer_schema": oneof_schema,
                }
            },
        )

    spec = runner.last_spec
    assert spec is not None
    assert "oneOf" in spec.task  # raw schema embedded in the prompt
    assert "read the value" in spec.task
    assert dict(result.data) == {"value": 3}


async def test_extract_rejects_empty_task(make_fake_runner: Callable[[BaseModel], FakeRunner]) -> None:
    runner = _runner_returning({"calories_per_serving": 1, "summary": "x"}, _RECIPE_SCHEMA, make_fake_runner)
    mcp = build_server(runner)
    async with Client(mcp) as c:
        with pytest.raises(ToolError):
            await c.call_tool(
                "extract",
                {
                    "args": {
                        "site": "https://recipes.test/lasagna",
                        "task": "",
                        "answer_schema": _RECIPE_SCHEMA,
                    }
                },
            )
