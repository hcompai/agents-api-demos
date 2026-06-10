"""Generic CUA runner: drives one bounded session and validates the answer against a Pydantic model."""

import logging
import uuid
from typing import Generic, Protocol, TypeVar
from urllib.parse import urlsplit, urlunsplit

from hai_agents import Agent, AgentEnvironmentsItem, AsyncClient, Session, async_wait_for_session
from hai_agents.core import ApiError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

LOGGER = logging.getLogger(__name__)

# Extra wall-clock beyond ``max_time_s`` so the platform can finish writing the terminal
# answer after it stops the session.
_CLIENT_GRACE_S = 60.0

T = TypeVar("T", bound=BaseModel)


class CuaError(Exception):
    """Mcpify runtime failure (no usable answer, schema mismatch, platform error)."""


class RunSpec(BaseModel, Generic[T]):
    """One CUA invocation: what to run and how to bound it."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    task: str
    output_model: type[T]
    environments: list[AgentEnvironmentsItem]
    instructions: str
    max_steps: int = Field(default=20, ge=1)
    max_time_s: float = Field(default=180.0, gt=0)


class Runner(Protocol):
    """Anything that can execute a ``RunSpec`` — lets the registrar depend on a duck type."""

    async def run(self, spec: RunSpec[T]) -> T: ...


class CuaRunner:
    """Drives CUA sessions on an injected ``AsyncClient``."""

    def __init__(self, client: AsyncClient, base_url: str, agent_artifact: str) -> None:
        assert agent_artifact, "agent_artifact must be a non-empty identifier"
        self._client = client
        self._base_url = base_url
        self._agent_artifact = agent_artifact

    async def run(self, spec: RunSpec[T]) -> T:
        """Run one session whose final answer is forced into ``spec.output_model``'s schema.

        Raises:
            CuaError: The platform rejects the request, the session ends without a
                structured answer, or the answer fails to validate.
            TimeoutError: The session does not reach a terminal status within
                ``max_time_s + _CLIENT_GRACE_S`` seconds.
        """
        agent = Agent(
            name=f"mcpify-{uuid.uuid4().hex[:12]}",
            description="Ephemeral mcpify tool session.",
            environments=spec.environments,
            instructions=spec.instructions,
        )
        session = await self._create_session(agent, spec)
        # Logged on every session so a failed run is debuggable after the fact.
        LOGGER.info("agent view: %s", agent_view_url(self._base_url, session.id))

        result = await async_wait_for_session(
            self._client,
            session.id,
            timeout_seconds=spec.max_time_s + _CLIENT_GRACE_S,
        )

        if not isinstance(result.answer, dict):
            raise CuaError(f"session {session.id} ended in {result.status} without a structured answer")
        try:
            return spec.output_model.model_validate(result.answer)
        except ValidationError as exc:
            raise CuaError(f"answer did not match {spec.output_model.__name__}: {exc}") from exc

    async def _create_session(self, agent: Agent, spec: RunSpec[T]) -> Session:
        # Separate hook so tests can subclass to observe the new session id (see _RecordingRunner).
        try:
            session: Session = await self._client.sessions.create_session(
                agent=agent,
                messages=spec.task,
                max_steps=spec.max_steps,
                max_time_s=spec.max_time_s,
                idle_timeout_s=None,  # one-shot: terminate when the agent answers
                answer_format=spec.output_model.model_json_schema(),
                agent_artifact=self._agent_artifact,
            )
            return session
        except ApiError as exc:
            raise CuaError(f"session creation failed: {exc}") from exc


def agent_view_url(base_url: str, trajectory_id: str) -> str:
    """``https://agp.<region>.…`` + id  →  ``https://dashboard.<region>.…/agent-view/<id>``."""
    if not trajectory_id:
        raise ValueError("trajectory_id must be non-empty")
    parts = urlsplit(base_url)
    if not parts.scheme or parts.hostname is None:
        raise ValueError(f"url missing scheme/host: {base_url!r}")
    host = parts.hostname
    dashboard_host = "dashboard." + host[len("agp.") :] if host.startswith("agp.") else host
    return urlunsplit((parts.scheme, dashboard_host, f"/agent-view/{trajectory_id}", "", ""))
