# Changelog

## v1.1.1 — 2026-09-04

- Friendly `status` message instead of a traceback when the usage API returns 429

## v1.1.0 — 2026-09-04

- Once-a-day update check against GitHub releases; an "Update available" item appears in the menu when a newer version exists
- Header buttons: usage stats (chart icon) and support ($) with tooltips; removed the text menu items and version line
- Fixed-width warning row so long messages never widen the menu
- Back off for 5 minutes when the usage API returns 429 (manual refresh still fetches immediately)
- Published on PyPI and via the tilbertbalaban/tap Homebrew tap


## v1.0.0 — 2026-09-02

First release.

- macOS menu bar ring gauges: session (5-hour) limit in green and 7-day limit in purple, percent inside, with the session reset countdown next to them
- Dropdown with a large session donut (7-day limit as a thin outer arc) and one row per limit showing "Today 6:10 PM"-style reset times
- Header with refresh and support ($) icon buttons
- Rings turn orange at 80% or on elevated severity, red with `!` at 100%
- Reads the Claude Code OAuth token from the macOS Keychain (falls back to `~/.claude/.credentials.json`), polls `api.anthropic.com/api/oauth/usage` every 60s; the token is sent nowhere else
- Graceful states for missing credentials, expired token, offline, and a rate-limited usage API (keeps last known data)
- `status` subcommand for terminal output, `autostart on|off` for a login LaunchAgent
