# Changelog

## v1.0.0 — 2026-09-02

First release.

- macOS menu bar ring gauges: session (5-hour) limit in green and 7-day limit in purple, percent inside, with the session reset countdown next to them
- Dropdown with a large session donut (7-day limit as a thin outer arc) and one row per limit showing "Today 6:10 PM"-style reset times
- Header with refresh and support ($) icon buttons
- Rings turn orange at 80% or on elevated severity, red with `!` at 100%
- Reads the Claude Code OAuth token from the macOS Keychain (falls back to `~/.claude/.credentials.json`), polls `api.anthropic.com/api/oauth/usage` every 60s; the token is sent nowhere else
- Graceful states for missing credentials, expired token, offline, and a rate-limited usage API (keeps last known data)
- `status` subcommand for terminal output, `autostart on|off` for a login LaunchAgent
