"""Read Claude Code OAuth credentials and fetch the account's rate limits.

Standard library only, so everything here is unit-testable without a Mac GUI.
"""

import json
import os
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
KEYCHAIN_SERVICE = "Claude Code-credentials"
CREDENTIALS_FILE = Path.home() / ".claude" / ".credentials.json"
CACHE_FILE = Path.home() / "Library" / "Caches" / "claude-limits-bar" / "usage.json"
CACHE_MAX_AGE = 3600
REQUEST_TIMEOUT = 15

WARN_PERCENT = 80


class CredentialsNotFound(Exception):
    """No Claude Code OAuth token in the Keychain or ~/.claude/.credentials.json."""


class TokenRejected(Exception):
    """The API returned 401/403 — the stored token is expired or revoked."""


class UsageRateLimited(Exception):
    """The usage endpoint itself returned 429 — back off, keep last data."""


@dataclass
class Limit:
    kind: str            # "session", "weekly_all", "weekly_scoped", ...
    label: str           # human-readable, e.g. "Session (5h)"
    percent: float
    severity: str        # "normal" | anything else means Anthropic flags it
    resets_at: Optional[datetime]
    is_active: bool

    @property
    def exhausted(self) -> bool:
        return self.percent >= 100

    @property
    def warning(self) -> bool:
        return self.percent >= WARN_PERCENT or self.severity not in ("normal", "")


def _read_keychain() -> Optional[str]:
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None


def _read_credentials_file() -> Optional[str]:
    try:
        return CREDENTIALS_FILE.read_text()
    except OSError:
        return None


def get_access_token() -> str:
    raw = _read_keychain() or _read_credentials_file()
    if not raw:
        raise CredentialsNotFound()
    return parse_access_token(raw)


def parse_access_token(raw: str) -> str:
    try:
        token = json.loads(raw).get("claudeAiOauth", {}).get("accessToken")
    except (json.JSONDecodeError, AttributeError):
        raise CredentialsNotFound()
    if not token:
        raise CredentialsNotFound()
    return token


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if ctx.cert_store_stats().get("x509_ca"):
        return ctx
    # python.org macOS builds ship without a CA bundle unless the user ran
    # "Install Certificates.command" — fall back to certifi or the system bundle.
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    if os.path.exists("/etc/ssl/cert.pem"):
        return ssl.create_default_context(cafile="/etc/ssl/cert.pem")
    return ctx


def fetch_usage(token: str) -> dict:
    req = urllib.request.Request(USAGE_URL, headers={
        "Authorization": "Bearer " + token,
        "anthropic-beta": "oauth-2025-04-20",
        "Content-Type": "application/json",
        "User-Agent": "claude-limits-bar",
    })
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=_ssl_context()) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise TokenRejected() from e
        if e.code == 429:
            raise UsageRateLimited() from e
        raise


def save_cache(data: dict, path: Path = CACHE_FILE) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"saved_at": time.time(), "data": data}))
    except OSError:
        pass


def load_cache(path: Path = CACHE_FILE, max_age: float = CACHE_MAX_AGE) -> Optional[dict]:
    """Last successful usage response if it is recent enough, else None."""
    try:
        payload = json.loads(path.read_text())
        if time.time() - float(payload["saved_at"]) > max_age:
            return None
        return payload["data"]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def get_limits() -> List[Limit]:
    return parse_limits(fetch_usage(get_access_token()))


def parse_limits(data: dict) -> List[Limit]:
    limits = []
    for item in data.get("limits") or []:
        resets_at = _parse_iso(item.get("resets_at"))
        limits.append(Limit(
            kind=item.get("kind") or "",
            label=_label(item),
            percent=float(item.get("percent") or 0),
            severity=item.get("severity") or "normal",
            resets_at=resets_at,
            is_active=bool(item.get("is_active")),
        ))
    return limits


def _label(item: dict) -> str:
    kind = item.get("kind") or ""
    if kind == "session":
        return "5-Hour Limit"
    if kind == "weekly_all":
        return "7-Day Limit"
    if kind == "weekly_scoped":
        model = ((item.get("scope") or {}).get("model") or {}).get("display_name")
        return "7-Day (%s)" % model if model else "7-Day (scoped)"
    return kind.replace("_", " ").capitalize() or "Limit"


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


# --- display helpers ---------------------------------------------------------

def primary_limit(limits: List[Limit]) -> Optional[Limit]:
    """What to show in the menu bar: the session limit by default (it is what
    usually triggers "Too many requests"), unless another limit is worse and
    already in warning territory."""
    if not limits:
        return None
    session = next((l for l in limits if l.kind == "session"), None)
    worst = max(limits, key=lambda l: l.percent)
    if worst.warning and (session is None or worst.percent > session.percent):
        return worst
    return session or worst


def time_until(resets_at: Optional[datetime], now: Optional[datetime] = None) -> str:
    if resets_at is None:
        return "?"
    now = now or datetime.now(timezone.utc)
    seconds = (resets_at - now).total_seconds()
    if seconds <= 0:
        return "now"
    minutes = int(seconds // 60)
    days, minutes = divmod(minutes, 1440)
    hours, minutes = divmod(minutes, 60)
    if days:
        return "%dd %dh" % (days, hours)
    if hours:
        return "%dh %02dm" % (hours, minutes)
    return "%dm" % max(minutes, 1)


def local_reset_time(resets_at: Optional[datetime], now: Optional[datetime] = None) -> str:
    if resets_at is None:
        return "?"
    now = (now or datetime.now(timezone.utc)).astimezone()
    local = resets_at.astimezone()
    if local.date() == now.date():
        return local.strftime("%H:%M")
    return local.strftime("%a %H:%M")


def reset_label(resets_at: Optional[datetime], now: Optional[datetime] = None) -> str:
    """Reset moment the way the menu rows show it: "Today 6:10 PM", "Sep 5 1 AM"."""
    if resets_at is None:
        return "?"
    now_local = (now or datetime.now(timezone.utc)).astimezone()
    local = resets_at.astimezone()
    time_part = local.strftime("%-I %p") if local.minute == 0 else local.strftime("%-I:%M %p")
    if local.date() == now_local.date():
        return "Today " + time_part
    return local.strftime("%b %-d ") + time_part


def bar_title(limits: List[Limit], now: Optional[datetime] = None) -> str:
    p = primary_limit(limits)
    if p is None:
        return "✳ ?"
    if p.exhausted:
        return "✳ ⛔ %s" % time_until(p.resets_at, now)
    prefix = "✳ ⚠️ " if any(l.warning for l in limits) else "✳ "
    return "%s%d%% · %s" % (prefix, round(p.percent), time_until(p.resets_at, now))


def limit_line(limit: Limit, now: Optional[datetime] = None) -> str:
    return "%s: %d%% — resets %s (in %s)" % (
        limit.label,
        round(limit.percent),
        local_reset_time(limit.resets_at, now),
        time_until(limit.resets_at, now),
    )
