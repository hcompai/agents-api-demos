"""Helpers for constructing the cloud browser environment a tool drives."""

from hai_agents import Environment_Web

_DEFAULT_WIDTH = 1280
_DEFAULT_HEIGHT = 800


def browser_env(start_url: str) -> Environment_Web:
    """Build the inline cloud web environment a tool drives.

    A catalog-id ``str`` would also be valid in ``Agent.environments`` (the env-agnostic
    seam), but every shipped tool today binds to an inline headless browser.

    ``mode`` is left unset (``None``) so it is omitted from the wire and the server applies its
    own default (currently ``visual``). Omitting keeps us forward-compatible if the field's
    values change, and avoids pinning a default the backend owns.

    Args:
        start_url: The URL the browser should navigate to as it boots the session.

    Returns:
        A configured ``Environment_Web`` object ready to slot into ``Agent.environments``.
    """
    return Environment_Web(
        id="browser",
        headless=True,
        width=_DEFAULT_WIDTH,
        height=_DEFAULT_HEIGHT,
        start_url=start_url,
    )
