"""Tests for ``links.agent_view_url_from_id`` — the AGP -> dashboard URL transform."""

import pytest

from examples.mcpify_anything.links import agent_view_url_from_id


def test_from_id_builds_dashboard_url() -> None:
    assert (
        agent_view_url_from_id("https://agp.eu.hcompany.ai", "bc3f04f2-a2f0-40fd-8239-d3fa0921929b")
        == "https://dashboard.eu.hcompany.ai/agent-view/bc3f04f2-a2f0-40fd-8239-d3fa0921929b"
    )


def test_from_id_tolerates_trailing_slash_base() -> None:
    assert (
        agent_view_url_from_id("https://agp.eu.hcompany.ai/", "abc")
        == "https://dashboard.eu.hcompany.ai/agent-view/abc"
    )


def test_from_id_keeps_non_agp_host() -> None:
    # A non-AGP host (local stub or alternate deployment) must not have its host
    # rewritten — only the conventional ``agp.<region>`` prefix gets swapped to ``dashboard.``.
    assert agent_view_url_from_id("https://example.test", "xyz") == "https://example.test/agent-view/xyz"


def test_from_id_rejects_empty_id() -> None:
    with pytest.raises(ValueError):
        agent_view_url_from_id("https://agp.eu.hcompany.ai", "")


def test_from_id_rejects_missing_scheme() -> None:
    with pytest.raises(ValueError):
        agent_view_url_from_id("agp.eu.hcompany.ai", "abc")
