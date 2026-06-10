"""Tests for ``@browser_tool`` (decorator -> ToolSpec) and ``register_specs`` (ToolSpec -> FastMCP).

Covers the whole framework's static contract:
- signature introspection,
- ``list[T]`` -> ``_ListWrapper`` synthesis (with title + wire-format guards),
- registrar wiring (RunSpec construction, list-unwrap, input validation, runtime bounds),
- ``answer_model_factory`` per-call dynamic schemas (the [extract] mechanism).
"""

from collections.abc import Callable
from typing import Annotated, Any

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from hai_agents import Environment_Web
from pydantic import BaseModel, Field, HttpUrl, RootModel, ValidationError, WithJsonSchema

from tests.mcpify_anything._fakes import FakeRunner
from examples.mcpify_anything.tool import _OPERATOR_PREAMBLE, ToolSpec, browser_tool, register_specs


class _Item(BaseModel):
    name: str = Field(description="exact label as shown")


class _SearchInput(BaseModel):
    site: HttpUrl
    query: str = Field(min_length=1)


class _ObjAnswer(BaseModel):
    foo: str
    bar: int


class _Receipt(BaseModel):
    foo: str
    doubled: int
    captured_at: str


# ---------------------------------------------------------------------------
# decorator: signature -> ToolSpec
# ---------------------------------------------------------------------------


async def test_decorator_extracts_name_and_doc_from_function() -> None:
    @browser_tool(
        instructions="ins",
        site=lambda a: a.site,
        prompt=lambda a: f"on {a.site} for {a.query}",
    )
    async def my_search(args: _SearchInput, answer: list[_Item]) -> list[_Item]:
        """search a thing."""
        return answer

    assert isinstance(my_search, ToolSpec)
    assert my_search.name == "my_search"
    assert my_search.description == "search a thing."


async def test_decorator_uses_input_and_output_models_from_annotations() -> None:
    @browser_tool(
        instructions="ins",
        site=lambda a: a.site,
        prompt=lambda a: "t",
    )
    async def my_search(args: _SearchInput, answer: _ObjAnswer) -> _Receipt:
        """transform."""
        return _Receipt(foo=answer.foo, doubled=answer.bar * 2, captured_at="now")

    assert my_search.input_model is _SearchInput
    assert my_search.output_model is _Receipt
    # BaseModel answers are used directly, not wrapped.
    assert my_search.answer_model is _ObjAnswer


async def test_decorator_wraps_list_annotation_in_basemodel_with_items_field() -> None:
    @browser_tool(
        instructions="ins",
        site=lambda a: a.site,
        prompt=lambda a: "t",
    )
    async def my_search(args: _SearchInput, answer: list[_Item]) -> list[_Item]:
        """list."""
        return answer

    # ``list[T]`` is wrapped in a ``BaseModel`` with an ``items: list[T]`` field (NOT a
    # ``RootModel``) so the agent-side serialisation produces ``{"items": [...]}`` rather
    # than ``{"root": [...]}`` — the platform's regenerated class round-trips cleanly.
    assert issubclass(my_search.answer_model, BaseModel)
    assert not issubclass(my_search.answer_model, RootModel)
    parsed = my_search.answer_model.model_validate({"items": [{"name": "a"}, {"name": "b"}]})
    assert [i.name for i in parsed.items] == ["a", "b"]


async def test_list_wrapper_carries_a_python_identifier_title() -> None:
    # The platform regenerates a Python class from the answer schema's ``title``. Square
    # brackets in titles like ``RootModel[list[Item]]`` break that step — assert the title
    # is a valid Python identifier.
    @browser_tool(
        instructions="ins",
        site=lambda a: a.site,
        prompt=lambda a: "t",
    )
    async def my_search(args: _SearchInput, answer: list[_Item]) -> list[_Item]:
        """list."""
        return answer

    title = my_search.answer_model.model_json_schema()["title"]
    assert title == "_ItemList"
    assert title.isidentifier(), f"answer schema title {title!r} must be a Python identifier"


async def test_list_wrapper_schema_is_object_with_items_array() -> None:
    # The wire-format contract: agent receives a top-level object schema with an
    # ``items`` array property — not a top-level array. This is what makes the answer
    # round-trip through datamodel-code-generator without a ``{"root": [...]}`` wrapping.
    @browser_tool(
        instructions="ins",
        site=lambda a: a.site,
        prompt=lambda a: "t",
    )
    async def my_search(args: _SearchInput, answer: list[_Item]) -> list[_Item]:
        """list."""
        return answer

    schema = my_search.answer_model.model_json_schema()
    assert schema["type"] == "object"
    assert schema["required"] == ["items"]
    assert schema["properties"]["items"]["type"] == "array"


async def test_answer_model_rejects_bare_list_payload_for_list_annotation() -> None:
    # The wrapper expects ``{"items": [...]}``; a bare list must be rejected loudly.
    @browser_tool(
        instructions="ins",
        site=lambda a: a.site,
        prompt=lambda a: "t",
    )
    async def my_search(args: _SearchInput, answer: list[_Item]) -> list[_Item]:
        """list."""
        return answer

    with pytest.raises(ValidationError):
        my_search.answer_model.model_validate([{"name": "a"}, {"name": "b"}])


async def test_answer_model_rejects_single_bare_item_for_list_annotation() -> None:
    # Safety property: a single bare item must NOT be silently wrapped into a one-element
    # list — that would mask "agent collapsed many results into one" as a successful answer.
    @browser_tool(
        instructions="ins",
        site=lambda a: a.site,
        prompt=lambda a: "t",
    )
    async def my_search(args: _SearchInput, answer: list[_Item]) -> list[_Item]:
        """list."""
        return answer

    with pytest.raises(ValidationError):
        my_search.answer_model.model_validate({"items": {"name": "a"}})


# ---------------------------------------------------------------------------
# registrar: spec -> FastMCP tool
# ---------------------------------------------------------------------------


async def test_register_specs_exposes_tool_under_its_name(make_fake_runner: Callable[[BaseModel], FakeRunner]) -> None:
    @browser_tool(
        instructions="ins",
        site=lambda a: a.site,
        prompt=lambda a: "t",
    )
    async def my_search(args: _SearchInput, answer: list[_Item]) -> list[_Item]:
        """list."""
        return answer

    runner = make_fake_runner(my_search.answer_model.model_validate({"items": [{"name": "x"}]}))
    mcp: FastMCP = FastMCP("test")
    register_specs([my_search], mcp, runner)

    async with Client(mcp) as c:
        names = {t.name for t in await c.list_tools()}
    assert "my_search" in names


async def test_register_specs_builds_runspec_with_prompt_and_schema_hint(
    make_fake_runner: Callable[[BaseModel], FakeRunner],
) -> None:
    @browser_tool(
        instructions="you read things",
        site=lambda a: a.site,
        prompt=lambda a: f"on {a.site} for {a.query}",
    )
    async def my_search(args: _SearchInput, answer: list[_Item]) -> list[_Item]:
        """list."""
        return answer

    runner = make_fake_runner(my_search.answer_model.model_validate({"items": [{"name": "z"}]}))
    mcp: FastMCP = FastMCP("test")
    register_specs([my_search], mcp, runner)

    async with Client(mcp) as c:
        await c.call_tool("my_search", {"args": {"site": "https://x.test", "query": "q"}})

    spec = runner.last_spec
    assert spec is not None
    assert spec.output_model is my_search.answer_model
    assert "on https://x.test/ for q" in spec.task
    assert "Return ONLY a JSON object matching this shape" in spec.task  # schema_hint header
    # The framework wraps every tool's persona with ``_OPERATOR_PREAMBLE`` so the JSON-output
    # protocol lives in one place (mirroring schema_hint on the user-message side).
    assert spec.instructions.startswith(_OPERATOR_PREAMBLE)
    assert "you read things" in spec.instructions
    env = spec.environments[0]
    assert isinstance(env, Environment_Web)
    assert env.start_url == "https://x.test/"


async def test_register_specs_unwraps_list_wrapper_before_calling_handler(
    make_fake_runner: Callable[[BaseModel], FakeRunner],
) -> None:
    captured: dict[str, object] = {}

    @browser_tool(
        instructions="ins",
        site=lambda a: a.site,
        prompt=lambda a: "t",
    )
    async def my_search(args: _SearchInput, answer: list[_Item]) -> list[_Item]:
        """list."""
        # User-facing contract: ``answer`` is a real list[_Item], not a wrapper.
        captured["answer_type"] = type(answer).__name__
        captured["names"] = [i.name for i in answer]
        return answer

    runner = make_fake_runner(my_search.answer_model.model_validate({"items": [{"name": "a"}, {"name": "b"}]}))
    mcp: FastMCP = FastMCP("test")
    register_specs([my_search], mcp, runner)

    async with Client(mcp) as c:
        result = await c.call_tool("my_search", {"args": {"site": "https://x.test", "query": "q"}})

    assert captured["answer_type"] == "list"
    assert captured["names"] == ["a", "b"]
    assert [item.name for item in result.data] == ["a", "b"]


async def test_register_specs_passes_basemodel_answer_directly_to_handler(
    make_fake_runner: Callable[[BaseModel], FakeRunner],
) -> None:
    @browser_tool(
        instructions="ins",
        site=lambda a: a.site,
        prompt=lambda a: "t",
    )
    async def my_search(args: _SearchInput, answer: _ObjAnswer) -> _Receipt:
        """transform."""
        return _Receipt(foo=answer.foo, doubled=answer.bar * 2, captured_at="captured")

    runner = make_fake_runner(_ObjAnswer(foo="hello", bar=5))
    mcp: FastMCP = FastMCP("test")
    register_specs([my_search], mcp, runner)

    async with Client(mcp) as c:
        result = await c.call_tool("my_search", {"args": {"site": "https://x.test", "query": "q"}})

    assert result.data.foo == "hello"
    assert result.data.doubled == 10
    assert result.data.captured_at == "captured"


async def test_register_specs_validates_input_against_input_model(
    make_fake_runner: Callable[[BaseModel], FakeRunner],
) -> None:
    @browser_tool(
        instructions="ins",
        site=lambda a: a.site,
        prompt=lambda a: "t",
    )
    async def my_search(args: _SearchInput, answer: list[_Item]) -> list[_Item]:
        """list."""
        return answer

    runner = make_fake_runner(my_search.answer_model.model_validate({"items": []}))
    mcp: FastMCP = FastMCP("test")
    register_specs([my_search], mcp, runner)

    async with Client(mcp) as c:
        # Empty ``query`` violates ``min_length=1`` — must be rejected before reaching the runner.
        with pytest.raises(ToolError):
            await c.call_tool("my_search", {"args": {"site": "https://x.test", "query": ""}})


async def test_register_specs_calls_handler_with_args(make_fake_runner: Callable[[BaseModel], FakeRunner]) -> None:
    captured_args: dict[str, object] = {}

    @browser_tool(
        instructions="ins",
        site=lambda a: a.site,
        prompt=lambda a: f"task for {a.query}",
    )
    async def my_search(args: _SearchInput, answer: list[_Item]) -> list[_Item]:
        """list."""
        captured_args["query"] = args.query
        captured_args["site"] = str(args.site)
        return answer

    runner = make_fake_runner(my_search.answer_model.model_validate({"items": [{"name": "z"}]}))
    mcp: FastMCP = FastMCP("test")
    register_specs([my_search], mcp, runner)

    async with Client(mcp) as c:
        await c.call_tool("my_search", {"args": {"site": "https://x.test", "query": "the-query"}})

    assert captured_args["query"] == "the-query"
    assert captured_args["site"] == "https://x.test/"


async def test_register_specs_uses_decorator_max_steps_and_time(
    make_fake_runner: Callable[[BaseModel], FakeRunner],
) -> None:
    @browser_tool(
        instructions="ins",
        site=lambda a: a.site,
        prompt=lambda a: "t",
        max_steps=7,
        max_time_s=42.0,
    )
    async def my_search(args: _SearchInput, answer: list[_Item]) -> list[_Item]:
        """list."""
        return answer

    runner = make_fake_runner(my_search.answer_model.model_validate({"items": []}))
    mcp: FastMCP = FastMCP("test")
    register_specs([my_search], mcp, runner)

    async with Client(mcp) as c:
        await c.call_tool("my_search", {"args": {"site": "https://x.test", "query": "q"}})

    spec = runner.last_spec
    assert spec is not None
    assert spec.max_steps == 7
    assert spec.max_time_s == 42.0


# ---------------------------------------------------------------------------
# answer_model_factory: per-call dynamic answer model (the [extract] mechanism)
# ---------------------------------------------------------------------------


class _DynamicInput(BaseModel):
    site: HttpUrl
    answer_schema: dict[str, Any]


def _build_dynamic_model(args: _DynamicInput) -> type[BaseModel]:
    Wrapped = Annotated[dict[str, Any], WithJsonSchema(args.answer_schema)]
    return RootModel[Wrapped]


async def test_factory_overrides_static_answer_model_per_call(
    make_fake_runner: Callable[[BaseModel], FakeRunner],
) -> None:
    @browser_tool(
        instructions="ins",
        site=lambda a: a.site,
        prompt=lambda a: "t",
        answer_model_factory=_build_dynamic_model,
    )
    async def dyn(args: _DynamicInput, answer: dict[str, Any]) -> dict[str, Any]:
        """dynamic."""
        return answer

    caller_schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "n": {"type": "integer"}},
        "required": ["name", "n"],
    }
    # The fake runner echoes the dict back, validated against whatever output_model the
    # registrar built per call. The factory's RootModel accepts any dict[str, Any].
    factory_model = _build_dynamic_model(
        _DynamicInput.model_validate({"site": "https://x.test", "answer_schema": caller_schema})
    )
    runner = make_fake_runner(factory_model.model_validate({"name": "ok", "n": 7}))
    mcp: FastMCP = FastMCP("test")
    register_specs([dyn], mcp, runner)

    async with Client(mcp) as c:
        result = await c.call_tool("dyn", {"args": {"site": "https://x.test", "answer_schema": caller_schema}})

    spec = runner.last_spec
    assert spec is not None
    # The platform-facing schema is built per call from ``args.answer_schema``. It carries
    # the caller's required fields (the auto-injected Pydantic ``title`` is incidental).
    rendered = spec.output_model.model_json_schema()
    assert rendered["required"] == ["name", "n"]
    assert rendered["properties"]["name"] == {"type": "string"}
    # The handler still receives a plain dict (registrar unwrapped RootModel.root).
    assert dict(result.data) == {"name": "ok", "n": 7}


async def test_factory_runs_fresh_on_every_call(make_fake_runner: Callable[[BaseModel], FakeRunner]) -> None:
    schemas_seen: list[dict[str, Any]] = []

    def _track(args: _DynamicInput) -> type[BaseModel]:
        schemas_seen.append(args.answer_schema)
        return _build_dynamic_model(args)

    @browser_tool(
        instructions="ins",
        site=lambda a: a.site,
        prompt=lambda a: "t",
        answer_model_factory=_track,
    )
    async def dyn(args: _DynamicInput, answer: dict[str, Any]) -> dict[str, Any]:
        """dynamic."""
        return answer

    schema_a = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
    schema_b = {"type": "object", "properties": {"b": {"type": "integer"}}, "required": ["b"]}
    runner = make_fake_runner(
        _build_dynamic_model(
            _DynamicInput.model_validate({"site": "https://x.test", "answer_schema": schema_a})
        ).model_validate({"a": "ok"})
    )
    mcp: FastMCP = FastMCP("test")
    register_specs([dyn], mcp, runner)

    async with Client(mcp) as c:
        await c.call_tool("dyn", {"args": {"site": "https://x.test", "answer_schema": schema_a}})
        await c.call_tool("dyn", {"args": {"site": "https://x.test", "answer_schema": schema_b}})

    # Factory runs on every invocation, not just at decoration time.
    assert schemas_seen == [schema_a, schema_b]


async def test_factory_default_none_keeps_static_answer_model(
    make_fake_runner: Callable[[BaseModel], FakeRunner],
) -> None:
    # Without a factory, the same static ``answer_model`` identity reaches RunSpec on every call.
    @browser_tool(
        instructions="ins",
        site=lambda a: a.site,
        prompt=lambda a: "t",
    )
    async def my_search(args: _SearchInput, answer: list[_Item]) -> list[_Item]:
        """list."""
        return answer

    assert my_search.answer_model_factory is None

    runner = make_fake_runner(my_search.answer_model.model_validate({"items": [{"name": "x"}]}))
    mcp: FastMCP = FastMCP("test")
    register_specs([my_search], mcp, runner)

    async with Client(mcp) as c:
        await c.call_tool("my_search", {"args": {"site": "https://x.test", "query": "q"}})

    spec = runner.last_spec
    assert spec is not None
    assert spec.output_model is my_search.answer_model
