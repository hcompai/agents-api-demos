"""The ``@browser_tool`` decorator and ``register_specs`` registrar — the core of the typed-tool framework."""

import inspect
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, Generic, TypeVar, cast, get_args, get_origin, get_type_hints

from fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, RootModel, create_model

from examples.mcpify_anything.envs import browser_env
from examples.mcpify_anything.runner import Runner, RunSpec
from examples.mcpify_anything.schema_hint import schema_hint

# Universal output protocol prepended to every tool's ``instructions`` at registration time.
# Symmetrical with how ``schema_hint(answer_model)`` is auto-appended to the user message: the
# framework owns the protocol on both sides so per-tool ``instructions=`` strings can stay pure
# persona / behavioural heuristics, with a single source of truth for "report as JSON, do not
# invent values".
_OPERATOR_PREAMBLE = (
    "Report exactly what is shown on the page as JSON. "
    "Do not invent fields or values. "
    "Do not wrap the answer in markdown or code fences."
)

InputT = TypeVar("InputT", bound=BaseModel)
# ``AnswerT`` is intentionally unbounded: handlers may take either a ``BaseModel`` directly or
# a ``list[BaseModel]`` (which the framework wraps in a synthesised ``_ListWrapper``). The
# isinstance/issubclass narrowing in ``_materialise_answer_model`` enforces the real contract.
AnswerT = TypeVar("AnswerT")
OutputT = TypeVar("OutputT")


class ToolSpec(BaseModel, Generic[InputT, AnswerT, OutputT]):
    """Declarative description of one MCP tool.

    Built by [browser_tool]; consumed by [register_specs]. This is the framework's
    only data type — every tool, regardless of shape (simple read / receipt / action),
    is exactly one ToolSpec record.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    name: str
    description: str
    input_model: type[InputT]
    answer_model: type[AnswerT]  # platform-facing; may be ``RootModel[list[T]]``
    output_model: object  # user fn's ``-> ...`` annotation; may be a generic like ``list[T]``
    instructions: str
    prompt: Callable[..., str]  # ``(InputT) -> str`` — Pydantic stores the callable as-is
    site: Callable[..., HttpUrl | str]  # ``(InputT) -> HttpUrl | str``
    handler: Callable[..., Awaitable[object]]  # ``(InputT, AnswerT) -> Awaitable[OutputT]``
    # Optional per-call override: when set, the registrar calls this with ``args`` to
    # build the answer model fresh on every invocation. Curated tools leave it None and
    # use the static ``answer_model``. The escape-hatch tool [extract] uses this to splice
    # the caller's JSON Schema (``WithJsonSchema(args.answer_schema)``) into the model.
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
) -> Callable[
    [Callable[[InputT, AnswerT], Awaitable[OutputT]]],
    ToolSpec[InputT, AnswerT, OutputT],
]:
    """Build a [ToolSpec] from a typed ``(args, answer) -> output`` async function.

    ``instructions`` vs ``prompt`` — the contract:
      - ``instructions`` is the system message: pure persona / behavioural heuristics
        ("You operate job-search UIs."). Static across calls. The framework prepends
        ``_OPERATOR_PREAMBLE`` (report as JSON, don't invent, no markdown) so per-tool
        strings should not restate the output protocol.
      - ``prompt`` is the user message: the per-call task, built from ``args``. The framework
        appends ``schema_hint(answer_model)`` so per-tool prompts should not restate the
        JSON shape either.

    Reads the function's real signature via ``inspect``/``get_type_hints`` — no annotation
    re-stamping, no cast. For ``answer: list[T]`` (or any non-BaseModel generic), the
    agent-facing answer model is ``RootModel[<annotation>]``; the registrar unwraps it
    via ``.root`` before the user function is called, so the handler always sees the
    natural Python shape.

    ``answer_model_factory`` is the escape hatch for dynamic-schema tools (notably
    [extract]). When provided, the registrar calls it with the validated ``args`` on every
    invocation to build the answer model fresh — letting the caller splice their JSON
    Schema into the platform's ``answer_format`` per call. Curated tools leave it ``None``.

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

    def _decorate(
        fn: Callable[[InputT, AnswerT], Awaitable[OutputT]],
    ) -> ToolSpec[InputT, AnswerT, OutputT]:
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

        answer_model = _materialise_answer_model(answer_annotation, fn_name=fn.__name__)

        # ``cast`` not ``# type: ignore``: ``input_model``/``answer_model`` come from runtime
        # annotation extraction (``get_type_hints``) so mypy can only narrow them to
        # ``type[BaseModel]``, but the surrounding ``Callable[[InputT, AnswerT], ...]`` proves
        # they ARE ``InputT``/``AnswerT`` for this specific decorator call.
        return ToolSpec(
            name=fn.__name__,
            description=(fn.__doc__ or "").strip(),
            input_model=cast("type[InputT]", input_model),
            answer_model=cast("type[AnswerT]", answer_model),
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


# ``ToolSpec[Any, Any, Any]`` because each ``SPECS`` tuple is heterogeneous — every entry has its
# own ``InputT/AnswerT/OutputT`` triple, and a single TypeVar can't express "any combination of
# parametrisations." Runtime correctness comes from ``ToolSpec``'s frozen Pydantic config.
def register_specs(specs: Iterable["ToolSpec[Any, Any, Any]"], mcp: FastMCP, runner: Runner) -> None:
    """Wire each ``ToolSpec`` into FastMCP, capturing the runner in a per-tool closure.

    Args:
        specs: The collection of tool specs to register, typically the example's ``SPECS`` tuple.
        mcp: The FastMCP server to attach each tool to.
        runner: The runner that executes ``RunSpec`` invocations behind every tool call.
    """
    for spec in specs:
        _register_one(spec, mcp, runner)


class _ListWrapper(BaseModel):
    """Marker base for auto-generated ``list[T]`` answer wrappers.

    The framework synthesises a ``BaseModel`` subclass ``<T>List`` with a single
    ``items: list[T]`` field for any ``answer: list[T]`` annotation. The marker lets the
    registrar detect the wrapping and unwrap ``.items`` before calling the user's handler
    (so the handler sees a real ``list[T]``). Why a BaseModel-with-field instead of a
    ``RootModel[list[T]]``: the platform regenerates a Python class from the answer schema
    and serialises the agent's answer through it — ``RootModel`` shapes round-trip as
    ``{"root": [...]}`` on the wire, which would force every consumer to know about the
    framework's quirk. The named field keeps the wire format a plain JSON object.
    """

    # Declared on the base so the access in ``_unwrap_answer`` typechecks. The concrete
    # element type ``T`` is bound at runtime by ``create_model(__base__=_ListWrapper,
    # items=(list[T], Field(...)))`` — mypy can't see that, hence the ``Any`` element.
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
    # ``RootModel[annotation]`` is metaprogramming: ``annotation`` is a runtime variable that
    # mypy refuses to evaluate as a static type parameter. Routing the subscript through an
    # ``Any``-typed alias defers it to runtime — Pydantic resolves it correctly there. The
    # final ``cast`` re-attaches the static return type for callers.
    root_model_alias: Any = RootModel
    try:
        return cast("type[BaseModel]", type(name, (root_model_alias[annotation],), {}))
    except TypeError as exc:
        raise TypeError(
            f"@browser_tool `{fn_name}`: cannot build a Pydantic answer model for annotation {annotation!r}"
        ) from exc


def _unwrap_answer(validated: BaseModel) -> object:
    if isinstance(validated, _ListWrapper):
        return validated.items
    if isinstance(validated, RootModel):
        return validated.root
    return validated


def _register_one(spec: "ToolSpec[Any, Any, Any]", mcp: FastMCP, runner: Runner) -> None:
    async def _wrapper(args: BaseModel) -> object:
        # Static answer model for curated tools; per-call override for dynamic-schema
        # tools like [extract]. The chosen model drives both the platform's
        # ``answer_format`` (via ``model_json_schema()``) and the validation contract.
        answer_model = spec.answer_model_factory(args) if spec.answer_model_factory is not None else spec.answer_model
        task = spec.prompt(args) + "\n" + schema_hint(answer_model)
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
    # Stamp annotations + signature so FastMCP introspects the *concrete* input/output
    # models (not the generic BaseModel above). Both surfaces are set so any
    # introspection path (function annotations or inspect.signature) sees the same thing.
    # ``__signature__`` is attached via ``setattr`` because the ``Callable`` protocol mypy uses
    # doesn't model arbitrary attribute assignment, even though Python functions accept it.
    _wrapper.__annotations__ = {"args": spec.input_model, "return": spec.output_model}
    setattr(
        _wrapper,
        "__signature__",
        inspect.Signature(
            parameters=[
                inspect.Parameter(
                    "args",
                    kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=spec.input_model,
                )
            ],
            return_annotation=spec.output_model,
        ),
    )
    mcp.tool(name=spec.name, description=spec.description)(_wrapper)
