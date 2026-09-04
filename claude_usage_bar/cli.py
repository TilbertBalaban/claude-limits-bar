import argparse
import plistlib
import subprocess
import sys
from pathlib import Path

from . import VERSION
from .limits import (
    CredentialsNotFound, TokenRejected, UsageRateLimited, get_limits, limit_line,
)

LAUNCH_AGENT = Path.home() / "Library" / "LaunchAgents" / "com.claude-usage-bar.plist"


def cmd_status() -> int:
    try:
        limits = get_limits()
    except CredentialsNotFound:
        print("No Claude Code credentials found — run `claude` and sign in first.")
        return 1
    except TokenRejected:
        print("Stored token was rejected — use Claude Code once so it refreshes the token.")
        return 1
    except UsageRateLimited:
        print("The usage API is rate-limited right now — try again in a minute.")
        return 1
    if not limits:
        print("No limits reported for this account.")
        return 0
    for limit in limits:
        print(limit_line(limit))
    return 0


def cmd_autostart(state: str) -> int:
    if state == "off":
        if LAUNCH_AGENT.exists():
            subprocess.run(["launchctl", "unload", str(LAUNCH_AGENT)], capture_output=True)
            LAUNCH_AGENT.unlink()
        print("Autostart disabled.")
        return 0
    executable = Path(sys.argv[0]).resolve()
    plist = {
        "Label": "com.claude-usage-bar",
        "ProgramArguments": [str(executable)],
        "RunAtLoad": True,
    }
    LAUNCH_AGENT.parent.mkdir(parents=True, exist_ok=True)
    LAUNCH_AGENT.write_bytes(plistlib.dumps(plist))
    subprocess.run(["launchctl", "unload", str(LAUNCH_AGENT)], capture_output=True)
    subprocess.run(["launchctl", "load", str(LAUNCH_AGENT)], capture_output=True)
    print("Autostart enabled (%s)." % LAUNCH_AGENT)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="claude-usage-bar",
        description="Claude limits and reset times in the macOS menu bar.",
    )
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("status", help="print current limits to the terminal")
    autostart = sub.add_parser("autostart", help="start automatically at login")
    autostart.add_argument("state", choices=["on", "off"])
    args = parser.parse_args()

    if args.command == "status":
        return cmd_status()
    if args.command == "autostart":
        return cmd_autostart(args.state)

    from .menubar import main as run_menubar
    run_menubar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
