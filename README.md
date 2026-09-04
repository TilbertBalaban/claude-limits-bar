# claude-usage-bar

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

**Claude Code limits and their reset times, always visible in the macOS menu bar.**

If you keep hitting *"Too many requests, please try again later"*, this shows you exactly how close you are to the limit and when it resets — before Claude Code cuts you off.

The menu bar shows two ring gauges — the session (5-hour) limit in green and the 7-day limit in purple, percent used inside each — plus the countdown until the session limit resets:

```
◔66 ◔12  3h 26m
```

Click it for the full picture: a large donut for the session limit (weekly as a thin outer arc) and one row per limit with its reset time:

```
✳ Claude Usage          ($) (↻)
        ╭─── 66% Used ───╮
◔66  5-Hour Limit     Today 6:10 PM
◔12  7-Day Limit         Sep 5 1 AM
◔18  7-Day (Fable)       Sep 5 1 AM
```

Rings turn orange at 80% or when Anthropic reports elevated severity, and red with `!` at 100% — the session (5-hour) limit is the one that usually triggers "Too many requests".

## How it works

Claude Code stores its OAuth token in the macOS Keychain (service `Claude Code-credentials`). This app reads that token and polls the same official endpoint the Claude apps use (`api.anthropic.com/api/oauth/usage`) once a minute. The token is sent **only** to `api.anthropic.com` — nowhere else, nothing is logged or stored.

Works on Pro and Max plans. Requires being signed in to Claude Code (`claude` → `/login`).

## Install

Requires macOS.

### Homebrew

```
brew install tilbertbalaban/tap/claude-usage-bar
```

### uv / pipx (needs Python 3.9+)

```
uv tool install claude-usage-bar
```

(or `pipx install claude-usage-bar`)

Then:

```
claude-usage-bar                # run the menu bar app
claude-usage-bar autostart on   # start automatically at login (LaunchAgent)
claude-usage-bar autostart off  # remove the login item
claude-usage-bar status         # print current limits to the terminal
```

## Updating

The app checks GitHub once a day and shows an **Update available** item in the menu when there's a newer version. To update:

```
brew upgrade claude-usage-bar        # Homebrew
uv tool upgrade claude-usage-bar     # uv
pipx upgrade claude-usage-bar        # pipx
```

Then quit the app from its menu and start it again (`claude-usage-bar`, or log out/in if you use `autostart on`).

## Support

If this app saves you from surprise rate limits, you can support development via the `$` button in the app or at [base.monobank.ua/tilbertbalaban](https://base.monobank.ua/tilbertbalaban).

## Development

```
git clone https://github.com/TilbertBalaban/claude-usage-bar
cd claude-usage-bar
python3 -m unittest discover -s tests -v
python3 -m claude_usage_bar.cli status
```

The data layer ([claude_usage_bar/limits.py](claude_usage_bar/limits.py)) is stdlib-only and fully unit-tested; only the menu bar shell ([claude_usage_bar/menubar.py](claude_usage_bar/menubar.py)) depends on PyObjC (AppKit).

## Troubleshooting

- **`✳ ?` in the menu bar** — open the menu for the reason: no credentials (sign in to Claude Code), an expired token (use Claude Code once — it refreshes the token itself), or no network.
- **`Too many requests` still happens at <100%** — the API reports utilization rounded to whole percent and with a small delay; treat the orange ring as "wrap up what you're doing".
