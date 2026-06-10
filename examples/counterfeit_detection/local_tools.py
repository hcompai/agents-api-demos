"""Local custom tools for the counterfeit-detection agent.

These functions run in *your* Python process, not in the agent's cloud browser: the SDK polling loop
executes them whenever the agent calls one and posts the result back into the session. That split is the
whole trick — the agent keeps browsing in the cloud while your machine renders reference screenshots with
Playwright and asks Holo for side-by-side visual verdicts.
"""

import base64
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from hai_agents import Tool, tool
from playwright.sync_api import sync_playwright

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"
MAX_REFERENCE_SNAPSHOTS = 3
HOLO_MODEL = "holo3-1-35b-a3b"
MODELS_BASE_URL = "https://api.hcompany.ai/v1/"
COMPARE_VERDICTS = ("VERY_LIKELY_COUNTERFEIT", "LIKELY_COUNTERFEIT", "INCONCLUSIVE", "LIKELY_AUTHENTIC")

logger = logging.getLogger(__name__)


class ChatCompletionsClient(Protocol):
    """Minimal protocol for the OpenAI-compatible client used by ``compare_to_genuine``."""

    @property
    def chat(self) -> Any: ...


@dataclass
class SnapshotStore:
    """Reference screenshots of the genuine product, cached for one run."""

    items: list[dict[str, str]] = field(default_factory=list)

    def add(self, label: str, path: Path) -> None:
        self.items.append({"label": label, "path": str(path)})

    def is_full(self) -> bool:
        return len(self.items) >= MAX_REFERENCE_SNAPSHOTS

    def is_empty(self) -> bool:
        return not self.items


@dataclass
class FindingsLog:
    """Counterfeit findings streamed out of the session via ``record_counterfeit``.

    Because the agent records each finding the moment it is confirmed, nothing is lost when the step or
    time budget trips mid-search — the log survives even a ``timed_out`` session.
    """

    items: list[dict[str, object]] = field(default_factory=list)

    def has(self, url: str) -> bool:
        return any(item["url"] == url for item in self.items)


def build_visual_tools(store: SnapshotStore, models_client: ChatCompletionsClient) -> list[Tool]:
    """Build the snapshot + compare tools bound to one run's state.

    Args:
        store: Snapshot cache the two tools share for this run.
        models_client: OpenAI-compatible client pointed at the H Models API, used for visual verdicts.

    Returns:
        ``[snapshot_genuine_product, compare_to_genuine]`` ready to pass to ``run_session(tools=...)``.
    """

    @tool(name="snapshot_genuine_product")
    def snapshot_genuine_product(url: str, label: str) -> str:
        """Cache a reference screenshot of the GENUINE product page.

        Call this 1-3 times at the very start of the task on the genuine URL, varying `label` each time
        (e.g. 'overview', 'logo_closeup', 'hardware'). compare_to_genuine uses these references later.
        """
        if store.is_full():
            return f"Already have {MAX_REFERENCE_SNAPSHOTS} references. No more saves needed."
        destination = SNAPSHOT_DIR / f"genuine_{len(store.items) + 1}_{label}.png"
        _capture(url, destination)
        store.add(label, destination)
        remaining = MAX_REFERENCE_SNAPSHOTS - len(store.items)
        return f"Saved reference #{len(store.items)} ('{label}'). {remaining} slots left."

    @tool(name="compare_to_genuine")
    def compare_to_genuine(suspect_url: str, note: str = "") -> str:
        """Get a side-by-side visual verdict for a suspect listing.

        Renders `suspect_url` on the investigator's machine, then compares it against the cached genuine
        references. `note` is your one-sentence reason for suspicion. Returns one line:
        VERY_LIKELY_COUNTERFEIT | LIKELY_COUNTERFEIT | INCONCLUSIVE | LIKELY_AUTHENTIC, then a colon,
        then one sentence of visual evidence.
        """
        if store.is_empty():
            return "ERROR: call snapshot_genuine_product on the genuine URL first."
        suspect_path = SNAPSHOT_DIR / f"suspect_{abs(hash(suspect_url))}.png"
        try:
            _capture(suspect_url, suspect_path)
        except Exception as exc:
            return f"INCONCLUSIVE: could not render {suspect_url} ({type(exc).__name__}: {exc})."
        return _holo_verdict(models_client, store, suspect_path, note)

    return [snapshot_genuine_product, compare_to_genuine]


def build_record_tool(log: FindingsLog) -> Tool:
    """Build the ``record_counterfeit`` tool bound to one run's findings log.

    Args:
        log: Findings accumulator the sweep CLI prints after the session ends.

    Returns:
        The tool, ready to append to the ``run_session(tools=...)`` list.
    """

    @tool(name="record_counterfeit")
    def record_counterfeit(
        url: str, confidence: str, compare_verdict: str, red_flags: list[str], reasoning: str
    ) -> str:
        """Stream one confirmed counterfeit finding to the investigator's results list.

        Call this once for EVERY counterfeit confirmed by compare_to_genuine, then keep searching.
        Never record the same URL twice. `confidence` is "high" | "medium" | "low"; `compare_verdict`
        is the line compare_to_genuine returned; `red_flags` is 2-5 short bullets; `reasoning` is one
        sentence.
        """
        if log.has(url):
            return f"Already recorded {url}. Move to the next suspect."
        log.items.append(
            {
                "url": url,
                "confidence": confidence,
                "compare_verdict": compare_verdict,
                "red_flags": red_flags,
                "reasoning": reasoning,
            }
        )
        return f"Recorded finding #{len(log.items)}: {url}. Keep searching for more."

    recorder: Tool = record_counterfeit
    return recorder


def _capture(url: str, destination: Path) -> None:
    """Render ``url`` in a local headless Chromium and save a full-page screenshot."""
    destination.parent.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            try:
                page.wait_for_load_state("networkidle", timeout=5_000)
            except Exception:
                logger.debug("networkidle never settled for %s; screenshotting anyway", url)
            page.screenshot(path=str(destination), full_page=True)
        finally:
            browser.close()


def _holo_verdict(models_client: ChatCompletionsClient, store: SnapshotStore, suspect_path: Path, note: str) -> str:
    """Ask Holo for a one-line verdict comparing the suspect screenshot to the genuine references."""
    instruction = (
        "You are comparing product photos. The first images show the GENUINE product. The last image is a "
        f"SUSPECT listing. Investigator note: {note or '(none)'}.\n"
        f"Respond on a single line with one of: {' | '.join(COMPARE_VERDICTS)}, then a colon, then ONE "
        "sentence of visual evidence (logo proportions, stitching, hardware, pricing banner, page quality)."
    )
    content: list[dict[str, object]] = [{"type": "text", "text": instruction}]
    for reference in store.items:
        content.append(_image_part(Path(reference["path"])))
    content.append(_image_part(suspect_path))
    response = models_client.chat.completions.create(
        model=HOLO_MODEL, messages=[{"role": "user", "content": content}], max_tokens=160
    )
    return str(response.choices[0].message.content).strip()


def _image_part(path: Path) -> dict[str, object]:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}}
