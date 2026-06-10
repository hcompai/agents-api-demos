"""Build a dashboard agent-view URL from an AGP base URL + a session/trajectory id."""

from urllib.parse import urlsplit, urlunsplit

_AGP_SUBDOMAIN = "agp."
_DASHBOARD_SUBDOMAIN = "dashboard."
_AGENT_VIEW_PATH = "/agent-view/"


def agent_view_url_from_id(base_url: str, trajectory_id: str) -> str:
    """Build the dashboard agent-view URL for a session/trajectory id off the AGP base URL.

    Needs only the id (no sharing), so a created session yields a viewable link even when
    its run later times out or fails — the runner logs this on every session start.

    Args:
        base_url: AGP base URL (``https://agp.<region>.hcompany.ai`` in production).
        trajectory_id: Session/trajectory id returned by ``create_session``.

    Returns:
        A ``https://dashboard.<region>.hcompany.ai/agent-view/<id>`` URL when the host
        carries the conventional ``agp.`` prefix; otherwise the same host with the
        agent-view path appended (useful for local stubs / non-AGP deployments).

    Raises:
        ValueError: ``trajectory_id`` is empty, or ``base_url`` is missing a scheme/host.
    """
    if not trajectory_id:
        raise ValueError("trajectory_id must be non-empty")
    parts = urlsplit(base_url)
    if not parts.scheme or parts.hostname is None:
        raise ValueError(f"url missing scheme/host: {base_url!r}")
    host = parts.hostname
    dashboard_host = _DASHBOARD_SUBDOMAIN + host[len(_AGP_SUBDOMAIN) :] if host.startswith(_AGP_SUBDOMAIN) else host
    return urlunsplit((parts.scheme, dashboard_host, f"{_AGENT_VIEW_PATH}{trajectory_id}", "", ""))
