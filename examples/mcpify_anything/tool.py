"""The ``@browser_tool`` decorator and ``register_specs`` registrar."""

import inspect
import json
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from typing import Any, TypeVar, cast, get_args, get_origin, get_type_hints

from fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, RootModel, create_model

from examples._shared import browser_env
from examples.mcpify_anything.runner import Runner, RunSpec
from examples.mcpify_anything.schema_hint import schema_hint

# Prepended to every tool's ``instructions`` so the JSON-output contract has one source of truth.
_OPERATOR_PREAMBLE = (Path(__file__).parent.parent / "prompts" / "operator_preamble.md").read_text().strip()

InputT = TypeVar("InputT", bound=BaseModel)
AnswerT = TypeVar("AnswerT")
OutputT = TypeVar("OutputT")


class ToolSpec(BaseModel):
    """Declarative description of one MCP tool."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    name: str
    description: str
    input_model: type[BaseModel]
    answer_model: type[BaseModel]
    output_model: object
    instructions: str
    prompt: Callable[..., str]
    site: Callable[..., HttpUrl | str]
    handler: Callable[..., Awaitable[object]]
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
    """Build a ``ToolSpec`` from a typed ``(args, answer) -> output`` async function.

    ``instructions`` is the static system message (the framework prepends ``_OPERATOR_PREAMBLE``).
    ``prompt`` builds the per-call user message (the framework appends ``schema_hint(answer_model)``).

    The function's annotations are the contract: ``answer: list[T]`` is wrapped in a synthesised
    model and unwrapped before the handler runs, so handlers always see the natural Python shape.
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
    """Wire each ``ToolSpec`` into FastMCP, capturing the runner in a per-tool closure."""
    for spec in specs:
        _register_one(spec, mcp, runner)


class _ListWrapper(BaseModel):
    """Marker base for auto-generated ``answer: list[T]`` wrappers (``items: list[T]``).

    Named-field rather than ``RootModel[list[T]]`` so the wire format is ``{"items": [...]}``
    instead of ``{"root": [...]}``. The registrar unwraps ``.items`` before the handler runs.
    """

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
    root_model_alias: Any = RootModel
    try:
        return cast("type[BaseModel]", type(name, (root_model_alias[annotation],), {}))
    except TypeError as exc:
        raise TypeError(
            f"@browser_tool `{fn_name}`: cannot build a Pydantic answer model for annotation {annotation!r}"
        ) from exc


def _answer_shape_hint(answer_model: type[BaseModel]) -> str:
    # ``schema_hint`` is strict; ``extract``'s caller-supplied schemas may fall outside it.
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
    # FastMCP introspects both ``__annotations__`` and ``__signature__``; set both to the
    # concrete models so the tool surfaces with proper schemas instead of generic BaseModel.
    _wrapper.__annotations__ = {"args": spec.input_model, "return": spec.output_model}
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
