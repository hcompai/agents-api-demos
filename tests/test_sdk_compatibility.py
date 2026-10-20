"""Credential-free checks for the SDK objects used by the demos."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from hai_agents import Client, SessionEvent, SessionRunResult
from pydantic import TypeAdapter

from examples._shared import _summarize_event
from examples.counterfeit_detection.local_tools import FindingsLog, build_record_tool
from examples.qa.mcp import debug, server


class SdkCompatibilityTests(unittest.TestCase):
    def test_review_round_trip(self) -> None:
        answer = {"verdict": "pass", "summary": "Reviewed the page."}
        requests: list[httpx.Request] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.method == "POST" and request.url.path == "/api/v2/sessions":
                return httpx.Response(
                    200,
                    json={
                        "id": "test-session",
                        "request": json.loads(request.content),
                        "status": {"status": "running"},
                        "created_at": "2026-10-20T00:00:00Z",
                    },
                )
            if request.url.path == "/api/v2/sessions/test-session/changes":
                return httpx.Response(200, json={"status": "completed", "answer": answer})
            if request.url.path == "/api/v2/sessions/test-session/status":
                return httpx.Response(200, json={"status": "completed"})
            raise AssertionError(f"Unexpected SDK request: {request.method} {request.url}")

        with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
            client = Client(api_key="test-key", httpx_client=transport)
            with patch.object(server, "_client", return_value=client):
                result = server.review_web_ui("https://example.com", "Review the page")

        self.assertEqual(result.model_dump(exclude_unset=True), answer)
        body = json.loads(requests[0].content)
        environment = body["agent"]["environments"][0]
        self.assertEqual(environment["kind"], "web")
        self.assertEqual(environment["start_url"], "https://example.com")
        self.assertEqual(environment["mode"], {"type": "visual", "width": 1280, "height": 800})
        self.assertEqual(body["max_steps"], 25)
        self.assertEqual(body["max_time_s"], 360.0)

    def test_typed_events_can_be_summarized_and_saved(self) -> None:
        event: SessionEvent = TypeAdapter(SessionEvent).validate_python(
            {
                "type": "AgentEvent",
                "timestamp": "2026-10-20T00:00:00Z",
                "data": {"kind": "observation_event", "text": "Page loaded"},
            }
        )
        self.assertEqual(_summarize_event(event), "AgentEvent: Page loaded")
        result: SessionRunResult = SessionRunResult(
            id="test-session", status="completed", events=[event], next_from_index=1, answer="Done"
        )
        with tempfile.TemporaryDirectory() as directory, patch.object(debug, "TRACES_DIR", Path(directory)):
            path = debug._save_trace("visual", "https://example.com", "Describe the page", 1.0, result)
            trace = json.loads(path.read_text())
        self.assertEqual(trace["events"][0], event.model_dump(mode="json"))

    def test_custom_tool_records_findings(self) -> None:
        log = FindingsLog()
        recorder = build_record_tool(log)
        arguments = {
            "url": "https://example.com/listing",
            "confidence": "high",
            "compare_verdict": "LIKELY_COUNTERFEIT",
            "red_flags": ["Wrong logo"],
            "reasoning": "The logo differs from the reference.",
        }
        self.assertEqual(recorder.definition()["name"], "record_counterfeit")
        recorder.fn(**arguments)
        self.assertEqual(log.items, [arguments])

    def test_tool_event_summary(self) -> None:
        event: SessionEvent = TypeAdapter(SessionEvent).validate_python(
            {
                "type": "AgentEvent",
                "timestamp": "2026-10-20T00:00:00Z",
                "data": {
                    "kind": "tool_result",
                    "tool_req": {"tool_name": "click", "args": {"x": 12, "y": 34}},
                    "result": "Clicked",
                },
            }
        )
        self.assertEqual(_summarize_event(event), "AgentEvent: click(x=12, y=34)")


if __name__ == "__main__":
    unittest.main()
