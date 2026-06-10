"""Test doubles for the ``mcpify_anything`` suite."""

from typing import TypeVar, cast

from pydantic import BaseModel

from examples.mcpify_anything.runner import RunSpec

T = TypeVar("T", bound=BaseModel)


class FakeRunner:
    """A ``Runner`` stub: records the last spec, returns a canned value."""

    def __init__(self, value: BaseModel) -> None:
        self._value = value
        self.last_spec: RunSpec[BaseModel] | None = None

    async def run(self, spec: RunSpec[T]) -> T:
        self.last_spec = cast(RunSpec[BaseModel], spec)
        return cast(T, self._value)
