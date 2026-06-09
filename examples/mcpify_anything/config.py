"""Boot-time settings — env vars -> validated Pydantic model consumed by ``compose_server``."""

import os

from hai_agents import HaiAgentsEnvironment
from pydantic import BaseModel, ConfigDict, Field

_API_KEY_ENV = "H_API_KEY"
_BASE_URL_ENV = "H_BASE_URL"
_AGENT_ARTIFACT_ENV = "H_AGENT_ARTIFACT"
_DEFAULT_BASE_URL = HaiAgentsEnvironment.EU.value
# Published agent build that matches the tool prompts (and bakes in the answer-format fix).
_DEFAULT_AGENT_ARTIFACT = "mcpify-anything-agent"


class Settings(BaseModel):
    """Frozen runtime settings consumed by ``compose_server``.

    Field-level ``min_length=1`` guards keep us loud if an env var is ever set to an empty
    string — a mid-conversation failure on the first tool call is harder to debug than
    blowing up at boot.
    """

    model_config = ConfigDict(frozen=True)

    api_key: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    agent_artifact: str = Field(min_length=1)


def settings() -> Settings:
    """Build the runtime settings from the environment.

    Raises:
        RuntimeError: ``H_API_KEY`` is not set — the only env var without a default.
    """
    api_key = os.environ.get(_API_KEY_ENV)
    if not api_key:
        raise RuntimeError(
            "H_API_KEY is not set. Copy .env.example to .env and add a key from "
            "https://portal.hcompany.ai, then re-run."
        )
    return Settings(
        api_key=api_key,
        base_url=os.environ.get(_BASE_URL_ENV, _DEFAULT_BASE_URL),
        agent_artifact=os.environ.get(_AGENT_ARTIFACT_ENV, _DEFAULT_AGENT_ARTIFACT),
    )
