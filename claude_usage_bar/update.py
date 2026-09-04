"""Once-a-day check for a newer release on GitHub."""

import json
import urllib.request
from typing import Optional

from . import VERSION
from .limits import _ssl_context

RELEASES_API = ("https://api.github.com/repos/"
                "TilbertBalaban/claude-usage-bar/releases/latest")
RELEASES_URL = "https://github.com/TilbertBalaban/claude-usage-bar/releases"
CHECK_INTERVAL_SECONDS = 24 * 3600


def latest_version(timeout: int = 10) -> Optional[str]:
    req = urllib.request.Request(RELEASES_API, headers={
        "User-Agent": "claude-usage-bar",
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
        tag = json.loads(resp.read().decode("utf-8")).get("tag_name") or ""
    return tag.lstrip("v") or None


def is_newer(candidate: Optional[str], current: str = VERSION) -> bool:
    try:
        parse = lambda v: tuple(int(part) for part in v.split("."))
        return parse(candidate) > parse(current)
    except (AttributeError, ValueError):
        return False


def available_update() -> Optional[str]:
    """Version string of a newer release, or None. Never raises."""
    try:
        latest = latest_version()
    except Exception:
        return None
    return latest if is_newer(latest) else None
