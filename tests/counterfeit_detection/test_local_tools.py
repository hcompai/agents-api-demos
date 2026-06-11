"""Unit tests for the counterfeit_detection local tools — no live API, no real browser."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from examples.counterfeit_detection import local_tools
from examples.counterfeit_detection.local_tools import (
    MAX_REFERENCE_SNAPSHOTS,
    FindingsLog,
    SnapshotStore,
    build_record_tool,
    build_visual_tools,
)


class _FakeModelsClient:
    """Stands in for the OpenAI client; returns a canned verdict and records the request."""

    def __init__(self, reply: str = "LIKELY_COUNTERFEIT: logo proportions off.") -> None:
        self.requests: list[dict[str, Any]] = []

        def create(**kwargs: Any) -> Any:
            self.requests.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply))])

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


@pytest.fixture
def fake_capture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Replace the Playwright render with a stub PNG write, sandboxed to tmp_path."""
    monkeypatch.setattr(local_tools, "SNAPSHOT_DIR", tmp_path)
    monkeypatch.setattr(local_tools, "_capture", lambda url, destination: destination.write_bytes(b"png"))


def test_snapshot_caps_at_max_references(fake_capture: None) -> None:
    store = SnapshotStore()
    snapshot, _ = build_visual_tools(store, _FakeModelsClient())

    for index in range(MAX_REFERENCE_SNAPSHOTS):
        assert f"Saved reference #{index + 1}" in snapshot(url="https://genuine.example", label=f"angle{index}")
    assert "No more saves" in snapshot(url="https://genuine.example", label="extra")
    assert len(store.items) == MAX_REFERENCE_SNAPSHOTS


def test_compare_requires_references_first(fake_capture: None) -> None:
    _, compare = build_visual_tools(SnapshotStore(), _FakeModelsClient())

    assert compare(suspect_url="https://suspect.example").startswith("ERROR")


def test_compare_sends_references_plus_suspect_and_returns_verdict(fake_capture: None) -> None:
    store = SnapshotStore()
    models_client = _FakeModelsClient(reply="VERY_LIKELY_COUNTERFEIT: stitching irregular.")
    snapshot, compare = build_visual_tools(store, models_client)
    snapshot(url="https://genuine.example", label="overview")
    snapshot(url="https://genuine.example", label="logo")

    verdict = compare(suspect_url="https://suspect.example", note="price 92% below retail")

    assert verdict == "VERY_LIKELY_COUNTERFEIT: stitching irregular."
    content = models_client.requests[0]["messages"][0]["content"]
    image_parts = [part for part in content if part["type"] == "image_url"]
    assert len(image_parts) == 3  # 2 references + 1 suspect
    assert "price 92% below retail" in content[0]["text"]


def test_record_counterfeit_deduplicates_by_url() -> None:
    log = FindingsLog()
    record = build_record_tool(log)
    kwargs = {
        "url": "https://replica.example/bag",
        "confidence": "high",
        "compare_verdict": "VERY_LIKELY_COUNTERFEIT: logo off.",
        "red_flags": ["1:1 replica wording", "95% below retail"],
        "reasoning": "Replica-cluster domain selling the same bag.",
    }

    assert "Recorded finding #1" in record(**kwargs)
    assert "Already recorded" in record(**kwargs)
    assert len(log.items) == 1
