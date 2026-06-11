"""Generic helpers shared by every example entry point.

QA-specific helpers (the reviewer instructions, ``ReviewResult`` model, agent-skill loader) live in
``examples.qa.shared`` so the QA recipe stays self-contained.
"""

import contextlib
import json
import logging
import os
import sys
import threading
import time
from typing import IO, Iterator

from hai_agents import Browser, Client, SessionRunResult, TrajectoryEvent, wait_for_session
from pydantic import BaseModel

_LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"


def browser_env(start_url: str) -> Browser:
    """Build the inline cloud browser environment a tool drives.

    A catalog-id ``str`` would also be valid in ``Agent.environments`` (the env-agnostic
    seam), but every shipped example today binds to an inline headless browser.

    ``mode`` is left unset (``None``) so it is omitted from the wire and the server applies its
    own default (currently ``visual``). Omitting keeps us forward-compatible if the field's
    values change, and avoids pinning a default the backend owns.

    Args:
        start_url: The URL the browser should navigate to as it boots the session.

    Returns:
        A configured ``Browser`` object ready to slot into ``Agent.environments``.
    """
    return Browser(
        id="browser",
        kind="web",  # the API's environment union discriminates on this tag; the SDK doesn't default it
        headless=True,
        width=1280,
        height=800,
        start_url=start_url,
    )


def require_api_key() -> str:
    """Return ``H_API_KEY`` from the environment or raise with a remediation hint."""
    api_key = os.environ.get("H_API_KEY")
    if not api_key:
        raise RuntimeError(
            "H_API_KEY is not set. Copy .env.example to .env and add a key from "
            "https://platform.hcompany.ai/settings/api-keys, then re-run."
        )
    return api_key


def setup_server_logging(level: int = logging.INFO) -> None:
    """Configure logging for an MCP server entry point.

    Logs go to stderr by default (Python's ``StreamHandler`` default), keeping stdout clean
    for the MCP stdio protocol.

    Args:
        level: Root logger level; defaults to ``INFO``.
    """
    logging.basicConfig(level=level, format=_LOG_FORMAT)


def setup_cli_logging(level: int = logging.WARNING, *, silence_http: bool = True) -> None:
    """Configure logging for a CLI entry point.

    Explicitly pins the stream to ``sys.stderr`` so stdout stays reserved for the JSON answer.

    Args:
        level: Root logger level; defaults to ``WARNING`` so CLI output stays uncluttered.
        silence_http: When ``True``, pin ``httpx``/``httpcore`` to ``WARNING`` regardless of
            the root level, so request-level chatter doesn't drown the JSON answer.
    """
    logging.basicConfig(level=level, stream=sys.stderr, format=_LOG_FORMAT)
    if silence_http:
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)


def print_structured_answer(result: SessionRunResult, model: type[BaseModel], started: float) -> None:
    """Print the session status to stderr and the validated answer JSON to stdout.

    Exits the process with a non-zero status if the session ended without a structured answer.

    Args:
        result: The completed ``run_session`` result.
        model: Pydantic model the answer must validate against.
        started: ``time.monotonic()`` timestamp captured before the session started.
    """
    print(f"completed in {time.monotonic() - started:.1f}s (status={result.status})", file=sys.stderr)
    if not isinstance(result.answer, dict):
        sys.exit(f"error: agent did not return a structured answer (status={result.status})")
    print(json.dumps(model.model_validate(result.answer).model_dump(), indent=2))


def _summarize_event(ev: TrajectoryEvent) -> str:
    """Best-effort one-line summary of a trajectory event.

    Shape-agnostic so it survives SDK schema changes: tries tool-call shape (``name`` +
    ``arguments``), then a small set of message-bearing keys, then recurses into common
    wrapper keys, then JSON-dumps as a last resort. No hard-coded event-type table.
    """
    body = _extract_body(ev.data)
    return f"{ev.type}: {_truncate(body)}" if body else ev.type


def _extract_body(data: object, depth: int = 0) -> str:
    """Pull a one-line string out of arbitrary event data, recursing into wrappers."""
    if depth > 2 or data is None:
        return ""
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        name, args = data.get("name"), data.get("arguments")
        if isinstance(name, str) and isinstance(args, dict):
            kv = ", ".join(f"{k}={_short_value(v)}" for k, v in list(args.items())[:3])
            return f"{name}({kv})"
        for key in ("message", "text", "content", "reasoning", "thought", "action", "url", "name"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value
        for key in ("event", "policy_event", "tool_call", "observation_event"):
            inner = _extract_body(data.get(key), depth + 1)
            if inner:
                return inner
        try:
            return json.dumps(data, default=str)
        except (TypeError, ValueError):
            return ""
    return str(data)


def _short_value(value: object) -> str:
    """Compact repr for a tool-call argument; truncates so the whole line stays short."""
    s = value if isinstance(value, str) else json.dumps(value, default=str)
    return s if len(s) <= 30 else s[:27] + "..."


def _truncate(s: str, n: int = 120) -> str:
    s = s.replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 3] + "..."


@contextlib.contextmanager
def _event_tailer(
    client: Client,
    session_id: str,
    *,
    started: float,
    stream: IO[str] = sys.stderr,
) -> Iterator[None]:
    """Single-line live status: spinner + elapsed time + latest event summary, refreshed in place.

    Two daemon threads share state: a poll thread long-polls ``get_session_changes`` and updates
    the ``latest`` message when new events arrive; a render thread ticks every ~150ms so the
    timer keeps moving even between events. Uses its own client-side cursor, so it runs alongside
    ``wait_for_session`` without conflict.

    Falls back to one heartbeat line every ~5s on a non-TTY stream (pipes/redirects can't move
    the cursor).
    """
    frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    stop = threading.Event()
    state_lock = threading.Lock()
    latest = "waiting for first event…"
    is_tty = hasattr(stream, "isatty") and stream.isatty()

    def _poll() -> None:
        nonlocal latest
        from_index = 0
        while not stop.is_set():
            try:
                changes = client.sessions.get_session_changes(
                    session_id,
                    from_index=from_index,
                    include_events=True,
                    wait_for_seconds=10,
                )
            except Exception as exc:  # network blips shouldn't kill the tail
                with state_lock:
                    latest = f"poll error: {exc}"
                if stop.wait(1.0):
                    return
                continue
            if changes is None:
                continue
            events = changes.new_events or []
            for ev in events:
                with state_lock:
                    latest = _summarize_event(ev)
                if stop.wait(0.3):  # let each event linger long enough to read
                    return
            from_index += len(events)

    def _render_tty() -> None:
        i = 0
        try:
            width = os.get_terminal_size().columns
        except OSError:
            width = 100
        while not stop.wait(0.15):
            elapsed = time.monotonic() - started
            with state_lock:
                msg = latest
            line = f"{frames[i % len(frames)]} [{elapsed:>5.0f}s] {msg}"
            if len(line) > width - 1:
                line = line[: width - 4] + "..."
            stream.write(f"\r\033[K{line}")
            stream.flush()
            i += 1

    def _render_plain() -> None:
        last_msg = None
        next_heartbeat = 5.0
        while not stop.wait(1.0):
            elapsed = time.monotonic() - started
            with state_lock:
                msg = latest
            if msg != last_msg or elapsed >= next_heartbeat:
                stream.write(f"[{elapsed:>5.0f}s] {msg}\n")
                stream.flush()
                last_msg = msg
                next_heartbeat = elapsed + 5.0

    poll_thread = threading.Thread(target=_poll, daemon=True)
    render_thread = threading.Thread(target=_render_tty if is_tty else _render_plain, daemon=True)
    poll_thread.start()
    render_thread.start()
    try:
        yield
    finally:
        stop.set()
        poll_thread.join(timeout=1.0)
        render_thread.join(timeout=0.5)
        if is_tty:
            stream.write("\r\033[K")
            stream.flush()


def run_session_streaming(client: Client, *, started: float, **create_params: object) -> SessionRunResult:
    """Like ``run_session``, but tails the trajectory and prints each event to stderr as it arrives.

    Splits ``run_session`` into ``create_session`` + ``wait_for_session`` so a daemon thread can
    print events live. No custom-tool support (the CLI demos that stream don't use ``tools=``);
    use ``run_session`` directly for that.

    Args:
        client: Authenticated SDK client.
        started: ``time.monotonic()`` captured before the call, used to label each event line.
        **create_params: Forwarded to ``client.sessions.create_session`` (agent, messages, etc.).
    """
    session = client.sessions.create_session(**create_params)  # type: ignore[arg-type]
    print(f"session {session.id} started", file=sys.stderr, flush=True)
    with _event_tailer(client, session.id, started=started):
        return wait_for_session(client, session.id)


@contextlib.contextmanager
def progress_spinner(
    label: str,
    *,
    budget_s: float | None = None,
    stream: IO[str] = sys.stderr,
) -> Iterator[None]:
    """Background heartbeat for long-running blocking calls like ``run_session``.

    On a TTY: animates a braille frame + elapsed seconds on a single line that the spinner
    rewrites in place. When ``stream`` is piped or redirected, falls back to a heartbeat line
    every 10s so logs still show the call is alive.

    Args:
        label: Short description shown next to the spinner (e.g. ``"flight-extractor running"``).
        budget_s: Optional total wall-clock budget; surfaced as ``"12s / 300s"`` so the user knows
            how much headroom is left.
        stream: Where to write progress; defaults to stderr so stdout stays clean for JSON output.
    """
    frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    stop = threading.Event()
    started = time.monotonic()
    is_tty = hasattr(stream, "isatty") and stream.isatty()

    def _tick() -> None:
        i = 0
        next_heartbeat = 10.0
        while not stop.wait(0.15 if is_tty else 1.0):
            elapsed = time.monotonic() - started
            budget = f" / {budget_s:.0f}s" if budget_s else ""
            if is_tty:
                stream.write(f"\r{frames[i % len(frames)]} {label} {elapsed:.0f}s{budget}")
                stream.flush()
                i += 1
            elif elapsed >= next_heartbeat:
                stream.write(f"{label} ... {elapsed:.0f}s{budget}\n")
                stream.flush()
                next_heartbeat += 10.0

    worker = threading.Thread(target=_tick, daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join(timeout=0.5)
        if is_tty:
            stream.write("\r\033[K")  # erase the spinner line so it doesn't bleed into the next output
            stream.flush()


def print_freeform_answer(result: SessionRunResult, started: float) -> None:
    """Print the session status to stderr and a free-form answer (string or JSON) to stdout.

    Exits the process with a non-zero status if the session produced no answer.

    Args:
        result: The completed ``run_session`` result.
        started: ``time.monotonic()`` timestamp captured before the session started.
    """
    print(f"completed in {time.monotonic() - started:.1f}s (status={result.status})", file=sys.stderr)
    if result.answer is None:
        sys.exit(f"error: no answer (status={result.status})")
    print(result.answer if isinstance(result.answer, str) else json.dumps(result.answer))
