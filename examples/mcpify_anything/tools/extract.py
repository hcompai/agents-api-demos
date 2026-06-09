"""Escape-hatch tool: drive a CUA against any URL with a caller-supplied JSON Schema."""

from typing import Annotated, Any

from pydantic import BaseModel, Field, HttpUrl, RootModel, WithJsonSchema

from examples.mcpify_anything.tool import browser_tool


class ExtractInput(BaseModel):
    site: HttpUrl
    task: str = Field(
        min_length=1,
        description=(
            "natural-language instruction for the CUA — do NOT restate the JSON shape, "
            "the framework appends `answer_schema` to the prompt automatically"
        ),
    )
    answer_schema: dict[str, Any] = Field(description="JSON Schema describing the desired return shape")


# Defined above the decorator because ``@browser_tool(...)`` binds the reference at module load.
def _build_answer_model(args: ExtractInput) -> type[BaseModel]:
    # ``WithJsonSchema`` makes the caller's schema the platform's ``answer_format`` while the
    # Python type stays ``dict``; the named subclass keeps the schema ``title`` a Python identifier.
    Wrapped = Annotated[dict[str, Any], WithJsonSchema(args.answer_schema)]

    class ExtractAnswer(RootModel[Wrapped]):
        pass

    return ExtractAnswer


@browser_tool(
    instructions="You browse websites and follow the caller's natural-language task.",
    site=lambda a: a.site,
    prompt=lambda a: a.task,
    answer_model_factory=_build_answer_model,
)
async def extract(args: ExtractInput, answer: dict[str, Any]) -> dict[str, Any]:
    """Open a site, follow a natural-language task, return JSON matching `answer_schema`.

    The escape hatch for sites/shapes that don't have a dedicated curated tool. Caller
    supplies the JSON Schema; the framework wires it into the platform's `answer_format`
    so the agent answers against the caller's contract.
    """
    return answer
