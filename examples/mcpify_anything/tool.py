"""The ``@browser_tool`` decorator and ``register_specs`` registrar — the core of the typed-tool framework."""

import inspect
import json
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, TypeVar, cast, get_args, get_origin, get_type_hints

from fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, RootModel, create_model

from examples._shared import browser_env
from examples.mcpify_anything.runner import Runner, RunSpec
from examples.mcpify_anything.schema_hint import schema_hint

# Prepended to every tool's ``instructions`` so the JSON-output protocol has a single source
# of truth (mirroring the auto-appended ``schema_hint`` on the user-message side).
_OPERATOR_PREAMBLE = (
    "Report exactly what is shown on the page as JSON. "
    "Do not invent fields or values. "
    "Do not wrap the answer in markdown or code fences."
)

InputT = TypeVar("InputT", bound=BaseModel)
# Unbounded: handlers may take a ``BaseModel`` or ``list[BaseModel]``; ``_materialise_answer_model``
# enforces the real contract at decoration time.
AnswerT = TypeVar("AnswerT")
OutputT = TypeVar("OutputT")


class ToolSpec(BaseModel):
    """Declarative description of one MCP tool.

    Built by [browser_tool]; consumed by [register_specs]. Every tool, regardless of
    shape, is exactly one ToolSpec record.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    name: str
    description: str
    input_model: type[BaseModel]
    answer_model: type[BaseModel]  # platform-facing; may be ``RootModel[list[T]]``
    output_model: object  # user fn's ``-> ...`` annotation; may be a generic like ``list[T]``
    instructions: str
    prompt: Callable[..., str]  # ``(InputT) -> str``
    site: Callable[..., HttpUrl | str]  # ``(InputT) -> HttpUrl | str``
    handler: Callable[..., Awaitable[object]]  # ``(InputT, AnswerT) -> Awaitable[OutputT]``
    # Per-call override for dynamic-schema tools ([extract]); curated tools leave it None
    # and use the static ``answer_model``.
    answer_model_factory: Callable[..., type[BaseModel]] | None
    max_steps: int
    max_time_s: float


def browser_tool(
    *,
    instructions: str,
    site: Callable[[InputT], HttpUrl | str],
    prompt: Callable[[InputT], str],
    answer_model_factory: Callable[[InputT], type[BaseModel]] | None = None,
    max_steps: int = 20,
    max_time_s: float = 180.0,
) -> Callable[[Callable[[InputT, AnswerT], Awaitable[OutputT]]], ToolSpec]:
    """Build a [ToolSpec] from a typed ``(args, answer) -> output`` async function.

    ``instructions`` vs ``prompt``: ``instructions`` is the static system message (persona /
    behavioural heuristics only — the framework prepends ``_OPERATOR_PREAMBLE``); ``prompt``
    is the per-call user message built from ``args`` (the framework appends
    ``schema_hint(answer_model)``, so per-tool prompts never restate the JSON shape).

    The function's annotations are the contract: ``answer: list[T]`` is wrapped in a
    synthesised model and unwrapped again before the handler runs, so handlers always see
    the natural Python shape.

    Args:
        instructions: Static system message describing the agent's role and behavioural rules.
        site: Function that resolves the start URL of the browser environment from ``args``.
        prompt: Function that builds the per-call user message from ``args``.
        answer_model_factory: Optional per-call factory yielding a fresh ``BaseModel`` whose
            JSON schema becomes the platform's ``answer_format``. Leave ``None`` for tools
            with a static answer shape; use it only for dynamic-schema tools like ``extract``.
        max_steps: Upper bound on the agent's CUA steps before the platform stops it.
        max_time_s: Upper bound on the agent's wall-clock seconds before the platform stops it.

    Returns:
        A decorator that turns the wrapped async function into a ``ToolSpec``.
    """

    def _decorate(fn: Callable[[InputT, AnswerT], Awaitable[OutputT]]) -> ToolSpec:
        hints = get_type_hints(fn)
        try:
            input_model = hints["args"]
            answer_annotation = hints["answer"]
            output_model = hints["return"]
        except KeyError as exc:
            raise TypeError(
                f"@browser_tool function `{fn.__name__}` must annotate (args, answer) -> output, "
                f"got hints={list(hints)}"
            ) from exc

        if not (isinstance(input_model, type) and issubclass(input_model, BaseModel)):
            raise TypeError(
                f"@browser_tool `{fn.__name__}`: `args` annotation must be a Pydantic BaseModel "
                f"subclass, got {input_model!r}"
            )

        return ToolSpec(
            name=fn.__name__,
            description=(fn.__doc__ or "").strip(),
            input_model=input_model,
            answer_model=_materialise_answer_model(answer_annotation, fn_name=fn.__name__),
            output_model=output_model,
            instructions=instructions,
            prompt=prompt,
            site=site,
            handler=fn,
            answer_model_factory=answer_model_factory,
            max_steps=max_steps,
            max_time_s=max_time_s,
        )

    return _decorate


def register_specs(specs: Iterable[ToolSpec], mcp: FastMCP, runner: Runner) -> None:
    """Wire each ``ToolSpec`` into FastMCP, capturing the runner in a per-tool closure.

    Args:
        specs: The collection of tool specs to register, typically the example's ``SPECS`` tuple.
        mcp: The FastMCP server to attach each tool to.
        runner: The runner that executes ``RunSpec`` invocations behind every tool call.
    """
    for spec in specs:
        _register_one(spec, mcp, runner)


class _ListWrapper(BaseModel):
    """Marker base for auto-generated ``answer: list[T]`` wrappers (``items: list[T]``).

    A named-field BaseModel rather than ``RootModel[list[T]]`` because RootModel shapes
    round-trip as ``{"root": [...]}`` on the platform wire; ``{"items": [...]}`` keeps the
    format a plain JSON object. The registrar unwraps ``.items`` before the handler runs.
    """

    # Declared on the base so ``_unwrap_answer`` typechecks; the concrete element type is
    # bound at runtime via ``create_model``, hence the ``Any`` element.
    items: list[Any] = Field(default_factory=list)


def _materialise_answer_model(annotation: object, *, fn_name: str) -> type[BaseModel]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    if get_origin(annotation) is list:
        args = get_args(annotation)
        if len(args) == 1 and isinstance(args[0], type):
            name = f"{args[0].__name__}List"
            return create_model(name, __base__=_ListWrapper, items=(annotation, Field(...)))
    name = f"{''.join(part.capitalize() for part in fn_name.split('_'))}Answer"
    # ``annotation`` is a runtime variable, so the RootModel subscript must go through an
    # ``Any``-typed alias for mypy; the ``cast`` re-attaches the static return type.
    root_model_alias: Any = RootModel
    try:
        return cast("type[BaseModel]", type(name, (root_model_alias[annotation],), {}))
    except TypeError as exc:
        raise TypeError(
            f"@browser_tool `{fn_name}`: cannot build a Pydantic answer model for annotation {annotation!r}"
        ) from exc


def _answer_shape_hint(answer_model: type[BaseModel]) -> str:
    # ``schema_hint`` is strict and renders only a subset of JSON Schema. Curated tools always
    # fall inside it; caller-supplied schemas ([extract]) may not — embed the raw schema then.
    try:
        return schema_hint(answer_model)
    except (KeyError, ValueError):
        schema = json.dumps(answer_model.model_json_schema(), separators=(",", ":"))
        return f"Return ONLY a JSON object matching this JSON Schema, with no other prose:\n{schema}"


def _unwrap_answer(validated: BaseModel) -> object:
    if isinstance(validated, _ListWrapper):
        return validated.items
    if isinstance(validated, RootModel):
        return validated.root
    return validated


def _register_one(spec: ToolSpec, mcp: FastMCP, runner: Runner) -> None:
    async def _wrapper(args: BaseModel) -> object:
        # The chosen model drives both the platform's ``answer_format`` and the validation contract.
        answer_model = spec.answer_model_factory(args) if spec.answer_model_factory is not None else spec.answer_model
        task = spec.prompt(args) + "\n" + _answer_shape_hint(answer_model)
        run_spec: RunSpec[BaseModel] = RunSpec(
            task=task,
            output_model=answer_model,
            environments=[browser_env(str(spec.site(args)))],
            instructions=f"{_OPERATOR_PREAMBLE}\n\n{spec.instructions}",
            max_steps=spec.max_steps,
            max_time_s=spec.max_time_s,
        )
        validated = await runner.run(run_spec)
        answer = _unwrap_answer(validated)
        return await spec.handler(args, answer)

    _wrapper.__name__ = spec.name
    _wrapper.__qualname__ = spec.name
    _wrapper.__doc__ = spec.description
    # Stamp both annotations and __signature__ so every FastMCP introspection path sees the
    # concrete input/output models rather than the generic BaseModel above.
    _wrapper.__annotations__ = {"args": spec.input_model, "return": spec.output_model}
    # typeshed doesn't model ``__signature__`` on Callable; the Any alias keeps mypy happy.
    untyped_wrapper: Any = _wrapper
    untyped_wrapper.__signature__ = inspect.Signature(
        parameters=[
            inspect.Parameter(
                "args",
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=spec.input_model,
            )
        ],
        return_annotation=spec.output_model,
    )
    mcp.tool(name=spec.name, description=spec.description)(_wrapper)
