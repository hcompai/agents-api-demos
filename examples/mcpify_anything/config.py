"""Boot-time settings — env vars validated into a Pydantic model."""

import os

from hai_agents import HaiAgentsEnvironment
from pydantic import BaseModel, ConfigDict, Field

from examples._shared import require_api_key


class Settings(BaseModel):
    """Frozen runtime settings; ``min_length=1`` rejects empty env vars at boot."""

    model_config = ConfigDict(frozen=True)

    api_key: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    agent_artifact: str = Field(min_length=1)


def settings() -> Settings:
    """Build settings from the environment.

    Raises:
        RuntimeError: ``H_API_KEY`` is not set.
    """
    return Settings(
        api_key=require_api_key(),
        base_url=os.environ.get("H_BASE_URL", HaiAgentsEnvironment.EU.value),
        agent_artifact=os.environ.get("H_AGENT_ARTIFACT", "mcpify-anything-agent"),
    )
