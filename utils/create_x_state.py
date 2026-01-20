#!/usr/bin/env python3
"""Create a Playwright storage_state file for X login."""
from __future__ import annotations

import argparse
from pathlib import Path

try:  # pragma: no cover - optional import
    from playwright.sync_api import sync_playwright
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "\N{CROSS MARK} playwright is not installed. Run 'pip install playwright' and "
        "'playwright install chromium'."
    ) from exc

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)
STEALTH_SNIPPET = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = window.chrome || { runtime: {} };
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
  parameters.name === 'notifications'
    ? Promise.resolve({ state: Notification.permission })
    : originalQuery(parameters)
);
"""


def _log(message: str) -> None:
    print(message)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a Playwright storage_state file for X login."
    )
    parser.add_argument(
        "--state-path",
        type=Path,
        default=Path("x_state.json"),
        help="Path to save the storage_state (default: x_state.json)",
    )
    parser.add_argument(
        "--login-url",
        default="https://x.com/i/flow/login",
        help="Login URL (default: https://x.com/i/flow/login)",
    )
    parser.add_argument(
        "--channel",
        default="chrome",
        help="Browser channel (default: chrome). Use '' to skip.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Run in headless mode (not recommended for login).",
    )
    parser.add_argument(
        "--no-stealth",
        action="store_true",
        help="Disable the anti-login wall injection.",
    )
    return parser.parse_args()


def _wait_for_enter(prompt: str) -> None:
    try:
        input(prompt)
        return
    except EOFError:
        pass

    try:
        with open("/dev/tty", "r+") as tty:
            tty.write(prompt)
            tty.flush()
            tty.readline()
    except Exception as exc:
        raise SystemExit(
            "\N{CROSS MARK} Could not read input from the terminal."
        ) from exc


def _launch_browser(playwright, *, headless: bool, channel: str | None):
    args = ["--disable-blink-features=AutomationControlled"]
    kwargs = {"headless": headless, "args": args}
    if channel:
        kwargs["channel"] = channel
    try:
        return playwright.chromium.launch(**kwargs)
    except Exception:
        if channel:
            kwargs.pop("channel", None)
            _log("\N{WARNING SIGN} Could not open Chrome; trying Chromium...")
            return playwright.chromium.launch(**kwargs)
        raise


def main() -> None:
    args = parse_args()
    state_path = args.state_path.expanduser()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    channel = args.channel.strip() if args.channel else None

    _log("\N{BIRD} Opening X login...")
    with sync_playwright() as p:
        browser = _launch_browser(p, headless=args.headless, channel=channel)
        context = browser.new_context(user_agent=USER_AGENT)
        if not args.no_stealth:
            context.add_init_script(STEALTH_SNIPPET)
        page = context.new_page()
        page.goto(args.login_url, wait_until="domcontentloaded")
        _wait_for_enter(
            "\N{WHITE HEAVY CHECK MARK} Sign in to X and press Enter here to save the session... "
        )
        context.storage_state(path=str(state_path))
        browser.close()

    _log(f"\N{FLOPPY DISK} storage_state saved to {state_path}")


if __name__ == "__main__":
    main()
