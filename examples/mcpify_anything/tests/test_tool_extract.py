"""Tests for the dynamic-schema escape-hatch tool ``extract``."""

from collections.abc import Callable
from typing import Any

import pytest
from fastmcp import Client
from pydantic import BaseModel

from examples.mcpify_anything.server import build_server
from examples.mcpify_anything.tests.conftest import FakeRunner
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


async def test_extract_is_listed_alongside_curated_tools(make_fake_runner: Callable[[BaseModel], FakeRunner]) -> None:
    runner = _runner_returning({"calories_per_serving": 400, "summary": "lasagna"}, _RECIPE_SCHEMA, make_fake_runner)
    mcp = build_server(runner)
    async with Client(mcp) as c:
        names = {tool.name for tool in await c.list_tools()}
    assert "extract" in names
    # Curated tools still registered (regression guard); ``get_product_prices`` ships here.
    assert "get_product_prices" in names


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
    # Caller's schema reaches the platform via ``answer_format``. The framework subclasses
    # the RootModel with a clean Python-identifier name so the platform's downstream
    # ``datamodel-code-generator`` step (which regenerates a Python class from the schema)
    # has a valid title to emit.
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


async def test_extract_rejects_empty_task(make_fake_runner: Callable[[BaseModel], FakeRunner]) -> None:
    runner = _runner_returning({"calories_per_serving": 1, "summary": "x"}, _RECIPE_SCHEMA, make_fake_runner)
    mcp = build_server(runner)
    async with Client(mcp) as c:
        with pytest.raises(Exception):
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


async def test_extract_uses_framework_default_runtime_budget(
    make_fake_runner: Callable[[BaseModel], FakeRunner],
) -> None:
    # ``extract`` relies on the decorator-level defaults (max_steps=20, max_time_s=180.0).
    # Per-call overrides are deliberately out of scope until a real caller needs them.
    runner = _runner_returning({"calories_per_serving": 1, "summary": "x"}, _RECIPE_SCHEMA, make_fake_runner)
    mcp = build_server(runner)
    async with Client(mcp) as c:
        await c.call_tool(
            "extract",
            {
                "args": {
                    "site": "https://recipes.test/lasagna",
                    "task": "read",
                    "answer_schema": _RECIPE_SCHEMA,
                }
            },
        )

    spec = runner.last_spec
    assert spec is not None
    assert spec.max_steps == 20
    assert spec.max_time_s == 180.0
