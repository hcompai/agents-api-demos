"""Shared fixtures for the mcpify_anything test suite."""

from collections.abc import Callable

import pytest
from hai_agents import AsyncClient
from pydantic import BaseModel

from tests.mcpify_anything._fakes import FakeRunner


@pytest.fixture
def client() -> AsyncClient:
    return AsyncClient(api_key="hk-test", base_url="https://agp.test")


@pytest.fixture
def make_fake_runner() -> Callable[[BaseModel], FakeRunner]:
    def _make(value: BaseModel) -> FakeRunner:
        return FakeRunner(value)

    return _make
