"""Test doubles used across the ``mcpify_anything`` test suite — importable as a normal module."""

from typing import TypeVar, cast

from pydantic import BaseModel

from examples.mcpify_anything.runner import RunSpec

T = TypeVar("T", bound=BaseModel)


class FakeRunner:
    """A ``Runner`` stub injected via ``build_server`` — records the last spec, returns a canned value.

    Lets tool tests drive the real server through dependency injection and assert on the
    ``RunSpec`` the tool built, without monkeypatching module globals. Satisfies the
    ``Runner`` Protocol structurally: ``run`` is generic on the spec's ``T`` and the cast
    keeps the canned value typed against whatever model the caller stored.
    """

    def __init__(self, value: BaseModel) -> None:
        """Bind the stub to the canned answer it should hand back from every ``run()``.

        Args:
            value: The validated answer the runner returns on every call.
        """
        self._value = value
        self.last_spec: RunSpec[BaseModel] | None = None

    async def run(self, spec: RunSpec[T]) -> T:
        self.last_spec = cast(RunSpec[BaseModel], spec)
        return cast(T, self._value)
