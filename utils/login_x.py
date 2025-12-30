#!/usr/bin/env python3
"""Manage X sessions with Playwright: persistent manual login and storage_state mode."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

from utils.x_likes_fetcher import (
    DEFAULT_LIKES_URL,
    DEFAULT_MAX_TWEETS,
    STEALTH_SNIPPET,
    collect_likes_from_page,
    fetch_likes_with_state,
)

LOGIN_URL = "https://x.com/i/flow/login"


def log(message: str) -> None:
    print(message)
    sys.stdout.flush()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Start a real Chrome with a persistent profile for manual login "
            "OR reuse an existing storage_state (allows --headless)."
        )
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=Path(".playwright") / "x-profile",
        help="Directory where the Chrome profile is saved. You can delete it to reset the session.",
    )
    parser.add_argument(
        "--likes-url",
        default=DEFAULT_LIKES_URL,
        help="Private URL opened after login to verify the session.",
    )
    parser.add_argument(
        "--export-state",
        type=Path,
        help="Save storage_state after a successful manual login to the given path.",
    )
    parser.add_argument(
        "--state",
        type=Path,
        help="Use this existing storage_state (JSON) to open likes directly.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Only valid with --state: run Chromium without UI when reusing storage_state.",
    )
    parser.add_argument(
        "--stop-at-url",
        help="URL of a previously processed tweet; stops when it appears in likes.",
    )
    parser.add_argument(
        "--max-tweets",
        type=int,
        default=DEFAULT_MAX_TWEETS,
        help=(
            "Hard limit of tweets to inspect on the likes page "
            f"(default: {DEFAULT_MAX_TWEETS})."
        ),
    )
    return parser.parse_args()


def manual_login_with_persistent_profile(
    profile_dir: Path,
    likes_url: str,
    max_tweets: int,
    stop_at_url: str | None,
    export_state: Path | None = None,
) -> None:
    profile_dir = profile_dir.expanduser()
    profile_dir.mkdir(parents=True, exist_ok=True)
    log(f"📁 Persistent profile: {profile_dir}")

    with sync_playwright() as playwright:
        try:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=False,
                channel="chrome",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                ],
            )
        except Exception as exc:  # pragma: no cover - depends on local environment
            raise SystemExit(
                "❌ Could not launch Chrome. Make sure Google Chrome is installed and accessible: "
                f"{exc}"
            ) from exc

        try:
            context.add_init_script(STEALTH_SNIPPET)
            page = context.pages[0] if context.pages else context.new_page()

            success, count, _, stop_found, _ = collect_likes_from_page(
                page, likes_url, max_tweets, stop_at_url
            )
            if success:
                log(
                    f"🙌 You were already authenticated. Visible liked tweets: {count}. "
                    f"Stop URL {'found' if stop_found else 'not found'}."
                )
            else:
                log(f"1️⃣  No active session. Opening {LOGIN_URL}…")
                page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
                log("   ℹ️  Complete the login manually in the Chrome window (use keyboard/mouse).")
                input("   ⏸️  Press Enter here when you see your timeline or X confirms the session.\n")

                success, count, _, stop_found, _ = collect_likes_from_page(
                    page, likes_url, max_tweets, stop_at_url
                )
                if success:
                    log(
                        f"   📊 Likes accessible after login. Visible articles: {count}. "
                        f"Stop URL {'found' if stop_found else 'not found'}."
                    )
                else:
                    log("   ❌ After manual login, the likes page is still not visible.")
                    log("      Check the window in case X asks for extra steps (2FA, captcha, etc.).")

            if export_state and success:
                export_path = export_state.expanduser()
                export_path.parent.mkdir(parents=True, exist_ok=True)
                context.storage_state(path=str(export_path))
                log(f"   💾 storage_state saved to {export_path}")
            elif export_state:
                log("   ⚠️  storage_state was not saved because the session is not active.")

            input("3️⃣  Press Enter when you want to close the window and keep the profile.\n")
        finally:
            context.close()
            log("🏁 Chrome closed. The profile stays on disk for reuse.")


def visit_with_storage_state(
    state_path: Path,
    likes_url: str,
    headless: bool,
    max_tweets: int,
    stop_at_url: str | None,
) -> None:
    try:
        urls, stop_found, total = fetch_likes_with_state(
            state_path,
            likes_url=likes_url,
            max_tweets=max_tweets,
            stop_at_url=stop_at_url,
            headless=headless,
        )
    except Exception as exc:  # pragma: no cover - friendly message
        raise SystemExit(f"❌ Error using storage_state: {exc}") from exc

    mode = "headless" if headless else "with UI"
    log(
        f"🏁 Valid session ({mode}). Visible tweets: {total}. "
        f"Stop URL {'found' if stop_found else 'not found'}."
    )
    if urls:
        log(f"   📌 New URLs detected: {len(urls)}")


def main() -> None:
    args = parse_args()
    if args.max_tweets <= 0:
        raise SystemExit("❌ --max-tweets must be greater than 0.")
    if args.state:
        visit_with_storage_state(
            args.state,
            args.likes_url,
            args.headless,
            args.max_tweets,
            args.stop_at_url,
        )
        return

    if args.headless:
        raise SystemExit("❌ --headless is only compatible with --state.")

    manual_login_with_persistent_profile(
        args.profile_dir,
        args.likes_url,
        args.max_tweets,
        args.stop_at_url,
        args.export_state,
    )


if __name__ == "__main__":
    main()
