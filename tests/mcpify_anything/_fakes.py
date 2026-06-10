"""Test doubles used across the ``mcpify_anything`` test suite — importable as a normal module."""

from typing import TypeVar, cast

from pydantic import BaseModel

from examples.mcpify_anything.runner import RunSpec

T = TypeVar("T", bound=BaseModel)


class FakeRunner:
    """A ``Runner`` stub injected via ``build_server`` — records the last spec, returns a canned value."""

    def __init__(self, value: BaseModel) -> None:
        """Bind the stub to the canned answer it returns from every ``run()``.

        Args:
            value: The validated answer the runner returns on every call.
        """
        self._value = value
        self.last_spec: RunSpec[BaseModel] | None = None

    async def run(self, spec: RunSpec[T]) -> T:
        self.last_spec = cast(RunSpec[BaseModel], spec)
        return cast(T, self._value)
