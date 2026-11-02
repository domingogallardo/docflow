#!/usr/bin/env python3
"""Collect, select, and like a fixed-corpus weekly X review."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import random
import re
import sys
import time as clock_time
from contextlib import contextmanager, suppress
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterator
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

if __package__ in {None, ""}:
    _REPO_ROOT = Path(__file__).resolve().parents[1]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

from playwright.sync_api import sync_playwright

import config as cfg
from utils.x_likes_fetcher import (
    LOGIN_WALL_HINTS,
    STEALTH_SNIPPET,
    TimelineTweet,
    _dismiss_cookie_prompt,
    collect_timeline_items_from_page,
)
from utils.tweet_to_markdown import (
    TWEET_DETAIL_WAIT_MS,
    _attach_tweet_detail_listener,
    _iter_tweet_results,
    _last_self_thread_status_id,
    _wait_for_tweet_detail,
)

MADRID = ZoneInfo("Europe/Madrid")
STATE_SCHEMA_VERSION = 2
SELECTION_SIZE = 50
DEFAULT_COLLECTION_ATTEMPTS = 2
DEFAULT_LIKE_ATTEMPTS = 2
DEFAULT_MAX_CONSECUTIVE_ERRORS = 5
CONFIRMED_LIKE_STATUSES = {"liked", "already_liked"}
CORPUS_FILENAME = "corpus.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _week_bounds(start_value: str | None) -> tuple[datetime, datetime, str]:
    if start_value:
        start_day = date.fromisoformat(start_value)
    else:
        today = datetime.now(MADRID).date()
        this_monday = today - timedelta(days=today.weekday())
        start_day = this_monday - timedelta(days=7)
    if start_day.weekday() != 0:
        raise ValueError("The weekly review must start on a Monday")
    start = datetime.combine(start_day, time.min, MADRID)
    end = start + timedelta(days=7)
    iso_year, iso_week, _ = start_day.isocalendar()
    return start, end, f"{iso_year}-W{iso_week:02d}"


def _state_dir() -> Path:
    return cfg.BASE_DIR / "state" / "x_weekly"


def _state_path(week_id: str) -> Path:
    return _state_dir() / f"{week_id}.json"


def _corpus_path() -> Path:
    return _state_dir() / CORPUS_FILENAME


def load_corpus(path: Path | None = None) -> tuple[tuple[str, int], ...]:
    """Load and validate the private fixed corpus stored outside the repository."""
    corpus_path = path or _corpus_path()
    try:
        raw = json.loads(corpus_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"X weekly corpus not found at {corpus_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"X weekly corpus is invalid JSON: {corpus_path}") from exc
    if not isinstance(raw, list) or len(raw) != SELECTION_SIZE:
        raise ValueError(f"X weekly corpus must contain exactly {SELECTION_SIZE} accounts")

    corpus: list[tuple[str, int]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Corpus item {index} must be an object")
        handle = str(item.get("handle") or "").strip().lstrip("@")
        weight = item.get("weight")
        if not handle or not re.fullmatch(r"[A-Za-z0-9_]+", handle):
            raise ValueError(f"Corpus item {index} has an invalid handle")
        if isinstance(weight, bool) or not isinstance(weight, int) or not 1 <= weight <= 100:
            raise ValueError(f"Corpus item {index} has an invalid weight")
        normalized = handle.casefold()
        if normalized in seen:
            raise ValueError(f"Corpus contains duplicate handle @{handle}")
        seen.add(normalized)
        corpus.append((handle, weight))
    return tuple(corpus)


def _corpus_payload(corpus: tuple[tuple[str, int], ...]) -> list[dict]:
    return [{"handle": f"@{handle}", "weight": weight} for handle, weight in corpus]


def _write_state(path: Path, payload: dict) -> None:
    """Atomically replace weekly state so interruptions cannot truncate it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        with suppress(FileNotFoundError):
            temporary.unlink()


def _read_state(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Weekly state is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Weekly state must be a JSON object: {path}")
    return payload


@contextmanager
def _state_lock(path: Path) -> Iterator[None]:
    """Prevent two automation invocations from mutating the same week."""
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"Another weekly review is already using {path}") from exc
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _tweet_id(url: str) -> str:
    match = re.search(r"/status/(\d+)", url)
    if not match:
        raise ValueError(f"Invalid tweet URL: {url}")
    return match.group(1)


def _candidate(item: TimelineTweet, *, source_handle: str, weight: int) -> dict:
    return {
        "id": _tweet_id(item.url),
        "url": item.url,
        "source_handle": f"@{source_handle}",
        "weight": weight,
        "author_handle": item.author_handle,
        "author_name": item.author_name,
        "published_at": item.time_datetime,
        "text": item.text,
        "text_truncated": item.text_truncated,
        "selected": False,
        "like_status": "pending",
    }


def _merge_candidates(existing: list[dict], additions: list[dict]) -> list[dict]:
    """Refresh harvested fields without losing editorial or Like state."""
    preserved_fields = {
        "selected", "rank", "summary", "topic", "like_status", "like_error",
        "like_attempts", "last_like_attempt_at", "like_confirmed_at",
    }
    merged = {str(candidate["id"]): candidate for candidate in existing}
    for addition in additions:
        tweet_id = str(addition["id"])
        previous = merged.get(tweet_id)
        if previous is None:
            merged[tweet_id] = addition
            continue
        preserved = {key: previous[key] for key in preserved_fields if key in previous}
        previous.update(addition)
        previous.update(preserved)
    return sorted(
        merged.values(),
        key=lambda candidate: candidate.get("published_at") or "",
        reverse=True,
    )


def _review_roll(week_id: str, tweet_id: str) -> float:
    digest = hashlib.sha256(f"{week_id}:{tweet_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def _prepare_review_pool(payload: dict) -> int:
    """Apply deterministic weighted exposure while keeping a viable pool."""
    candidates = payload.get("candidates", [])
    for candidate in candidates:
        roll = _review_roll(payload["week"], str(candidate["id"]))
        candidate["review_roll"] = round(roll, 10)
        candidate["sampled_for_review"] = roll < (int(candidate["weight"]) / 100)
        candidate.pop("review_promoted", None)

    target = min(SELECTION_SIZE, len(candidates))
    selected_count = sum(bool(candidate["sampled_for_review"]) for candidate in candidates)
    if selected_count < target:
        excluded = sorted(
            (candidate for candidate in candidates if not candidate["sampled_for_review"]),
            key=lambda candidate: (-int(candidate["weight"]), candidate["review_roll"]),
        )
        for candidate in excluded[: target - selected_count]:
            candidate["sampled_for_review"] = True
            candidate["review_promoted"] = True

    pool_count = sum(bool(candidate["sampled_for_review"]) for candidate in candidates)
    payload["review_pool_count"] = pool_count
    return pool_count


def _new_state(
    start: datetime,
    end: datetime,
    week_id: str,
    corpus: tuple[tuple[str, int], ...],
) -> dict:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "week": week_id,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "corpus": _corpus_payload(corpus),
        "candidates": [],
        "errors": [],
        "completed_handles": [],
        "review_pool_ready": False,
        "collection": {
            "status": "pending",
            "handles": {},
        },
    }


def _load_or_create_state(
    path: Path,
    start: datetime,
    end: datetime,
    week_id: str,
    corpus: tuple[tuple[str, int], ...],
) -> dict:
    if not path.exists():
        return _new_state(start, end, week_id, corpus)
    payload = _read_state(path)
    expected = {
        "week": week_id,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "corpus": _corpus_payload(corpus),
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise RuntimeError(f"Weekly state has an unexpected {key}: {path}")
    payload["schema_version"] = STATE_SCHEMA_VERSION
    payload.setdefault("candidates", [])
    payload.setdefault("completed_handles", [])
    payload.setdefault("errors", [])
    payload.setdefault("collection", {"status": "pending", "handles": {}})
    payload["collection"].setdefault("handles", {})
    return payload


def _record_collection_summary(payload: dict, *, status: str) -> None:
    collection = payload["collection"]
    collection.update(
        status=status,
        updated_at=_utc_now(),
        successful_handles=len(set(payload["completed_handles"])),
        failed_handles=len(payload["errors"]),
        candidate_count=len(payload["candidates"]),
        review_pool_count=payload.get("review_pool_count", 0),
    )


def collect_week(
    start_value: str | None,
    *,
    max_per_handle: int = 100,
    attempts_per_handle: int = DEFAULT_COLLECTION_ATTEMPTS,
    max_consecutive_errors: int = DEFAULT_MAX_CONSECUTIVE_ERRORS,
) -> Path:
    start, end, week_id = _week_bounds(start_value)
    state_path = _state_path(week_id)
    corpus = load_corpus()
    payload = _load_or_create_state(state_path, start, end, week_id, corpus)
    payload["completed_handles"] = list(dict.fromkeys(payload["completed_handles"]))
    payload["errors"] = list({error["handle"]: error for error in payload["errors"]}.values())
    collection = payload["collection"]
    collection.setdefault("started_at", _utc_now())
    collection["status"] = "running"
    payload["review_pool_ready"] = False

    state = cfg.TWEET_LIKES_STATE.expanduser()
    if not state.exists():
        raise FileNotFoundError(f"storage_state not found at {state}")
    if attempts_per_handle < 1:
        raise ValueError("attempts_per_handle must be at least 1")

    consecutive_errors = 0
    with sync_playwright() as playwright:
        for index, (handle, weight) in enumerate(corpus, 1):
            normalized_handle = f"@{handle}"
            if normalized_handle in payload["completed_handles"]:
                print(f"[{index:02d}/{len(corpus)}] @{handle} already collected")
                continue

            handle_state = collection["handles"].setdefault(normalized_handle, {"attempts": 0})
            last_error: Exception | None = None
            for attempt in range(1, attempts_per_handle + 1):
                print(
                    f"[{index:02d}/{len(corpus)}] @{handle} "
                    f"(weight {weight}, attempt {attempt}/{attempts_per_handle})"
                )
                handle_state["attempts"] = int(handle_state.get("attempts", 0)) + 1
                browser = None
                context = None
                page = None
                try:
                    browser = playwright.chromium.launch(headless=True, channel="chrome")
                    context = browser.new_context(storage_state=str(state))
                    context.add_init_script(STEALTH_SNIPPET)
                    page = context.new_page()
                    success, _, items, _, _ = collect_timeline_items_from_page(
                        page,
                        f"https://x.com/{handle}",
                        expected_author_handle=normalized_handle,
                        exclude_pinned=True,
                        include_reposts=False,
                        max_tweets=max_per_handle,
                        timeline_label=f"Weekly @{handle}",
                        since_datetime=start,
                        until_datetime=end,
                    )
                    if not success:
                        raise RuntimeError("timeline did not load")
                    additions = [
                        _candidate(item, source_handle=handle, weight=weight)
                        for item in items
                    ]
                    payload["candidates"] = _merge_candidates(payload["candidates"], additions)
                    payload["errors"] = [
                        error for error in payload["errors"]
                        if error.get("handle") != normalized_handle
                    ]
                    payload["completed_handles"].append(normalized_handle)
                    handle_state.update(
                        status="complete",
                        candidate_count=len(additions),
                        completed_at=_utc_now(),
                    )
                    handle_state.pop("error", None)
                    consecutive_errors = 0
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    handle_state.update(status="failed", error=str(exc), updated_at=_utc_now())
                finally:
                    if page is not None:
                        with suppress(Exception):
                            page.wait_for_timeout(
                                500
                                + random.Random(
                                    f"{week_id}:{handle}:{attempt}"
                                ).randint(0, 500)
                            )
                    if context is not None:
                        with suppress(Exception):
                            context.close()
                    if browser is not None:
                        with suppress(Exception):
                            browser.close()

            if last_error is not None:
                payload["errors"] = [
                    error for error in payload["errors"]
                    if error.get("handle") != normalized_handle
                ]
                payload["errors"].append(
                    {"handle": normalized_handle, "error": str(last_error)}
                )
                consecutive_errors += 1

            _prepare_review_pool(payload)
            _record_collection_summary(payload, status="running")
            _write_state(state_path, payload)

            if consecutive_errors >= max_consecutive_errors:
                payload["collection"]["status"] = "failed"
                payload["collection"]["failure_reason"] = (
                    f"Stopped after {consecutive_errors} consecutive profile failures"
                )
                _write_state(state_path, payload)
                raise RuntimeError(payload["collection"]["failure_reason"])

    _prepare_review_pool(payload)
    payload["review_pool_ready"] = True
    payload["collection"]["finished_at"] = _utc_now()
    final_status = "complete_with_errors" if payload["errors"] else "complete"
    _record_collection_summary(payload, status=final_status)
    _write_state(state_path, payload)
    print(
        f"Saved {len(payload['candidates'])} candidates "
        f"({payload['review_pool_count']} sampled for review) to {state_path}"
    )
    return state_path


def _selected(payload: dict) -> list[dict]:
    return [candidate for candidate in payload.get("candidates", []) if candidate.get("selected")]


def apply_selection(state_path: Path, selection_path: Path) -> None:
    """Apply a curated, ranked selection plan to a collected weekly state."""
    payload = _read_state(state_path)
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if not isinstance(selection, list) or len(selection) != SELECTION_SIZE:
        raise ValueError(f"The weekly selection must contain exactly {SELECTION_SIZE} items")

    required = {"id", "summary", "topic"}
    for index, item in enumerate(selection, 1):
        if not isinstance(item, dict) or not required.issubset(item):
            raise ValueError(f"Selection item {index} must contain id, summary, and topic")
        if not str(item["summary"]).strip() or not str(item["topic"]).strip():
            raise ValueError(f"Selection item {index} has an empty summary or topic")

    candidate_by_id = {
        str(candidate["id"]): candidate for candidate in payload.get("candidates", [])
    }
    selected_ids = [str(item["id"]) for item in selection]
    if len(set(selected_ids)) != len(selected_ids):
        raise ValueError("The weekly selection contains duplicate tweet IDs")
    missing = [tweet_id for tweet_id in selected_ids if tweet_id not in candidate_by_id]
    if missing:
        raise ValueError(f"Selected tweet IDs are missing from the corpus: {', '.join(missing)}")
    if payload.get("review_pool_ready"):
        outside_pool = [
            tweet_id for tweet_id in selected_ids
            if not candidate_by_id[tweet_id].get("sampled_for_review")
        ]
        if outside_pool:
            raise ValueError(
                "Selected tweet IDs are outside the weighted review pool: "
                + ", ".join(outside_pool)
            )

    existing_confirmed = {
        str(candidate["id"])
        for candidate in _selected(payload)
        if candidate.get("like_status") in CONFIRMED_LIKE_STATUSES
    }
    if existing_confirmed and set(selected_ids) != {
        str(candidate["id"]) for candidate in _selected(payload)
    }:
        raise RuntimeError("Cannot change the selection after any Like has been confirmed")

    for candidate in payload.get("candidates", []):
        candidate["selected"] = False
        candidate.pop("rank", None)
        candidate.pop("summary", None)
        candidate.pop("topic", None)
    for rank, item in enumerate(selection, 1):
        candidate = candidate_by_id[str(item["id"])]
        candidate.update(
            selected=True,
            rank=rank,
            summary=str(item["summary"]).strip(),
            topic=str(item["topic"]).strip(),
        )
    payload["selection"] = {
        "status": "complete",
        "selected_at": _utc_now(),
        "selected_count": len(selection),
        "source": str(selection_path),
    }
    _write_state(state_path, payload)
    print(f"Applied a selection of {len(selection)} tweets to {state_path}")


def _resolve_like_target(candidate: dict, payload: object | None) -> tuple[str, str]:
    author_handle = candidate.get("author_handle") or candidate.get("source_handle")
    target_id = _last_self_thread_status_id(
        payload,
        str(candidate["id"]),
        author_handle,
    )
    if target_id == str(candidate["id"]):
        return target_id, candidate["url"]
    handle = str(author_handle or "").lstrip("@")
    return target_id, f"https://x.com/{handle}/status/{target_id}"


class LikeAttemptError(RuntimeError):
    """A classified browser failure, persisted alongside the checkpoint."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def _failure_kind(exc: Exception) -> str:
    if isinstance(exc, LikeAttemptError):
        return exc.kind
    message = str(exc).lower()
    if any(word in message for word in ("login wall", "session invalid", "captcha")):
        return "authentication"
    return "transient"


def _pause(seconds: float) -> None:
    # Keep individual sleeps bounded, including during an automatic cooldown.
    remaining = seconds
    while remaining > 0:
        interval = min(remaining, 60)
        clock_time.sleep(interval)
        remaining -= interval


class _LikeSession:
    """Reuse authenticated Chrome context; isolate listeners in per-attempt pages."""

    def __init__(self, playwright, state: Path, state_path: Path):
        self.playwright = playwright
        self.state = state
        self.state_path = state_path
        self.browser = None
        self.context = None

    def new_page(self):
        if self.context is None:
            self.browser = self.playwright.chromium.launch(headless=True, channel="chrome")
            self.context = self.browser.new_context(storage_state=str(self.state))
            self.context.add_init_script(STEALTH_SNIPPET)
        return self.context.new_page()

    def close(self) -> None:
        if self.context is not None:
            with suppress(Exception):
                self.context.close()
        if self.browser is not None:
            with suppress(Exception):
                self.browser.close()
        self.context = self.browser = None


def _check_like_page(page, http_errors: list[dict]) -> None:
    if any(hint in (page.url or "") for hint in LOGIN_WALL_HINTS):
        raise LikeAttemptError("authentication", "Login wall or account challenge detected")
    if page.locator('iframe[src*="captcha"], [data-testid="LoginForm_Login_Button"]').count():
        raise LikeAttemptError("authentication", "Login wall or CAPTCHA detected")
    for item in http_errors:
        status = item["status"]
        if status in (401, 403):
            raise LikeAttemptError("authentication", f"X rejected access (HTTP {status})")
        if status == 429:
            raise LikeAttemptError("rate_limit", "X rate limit detected (HTTP 429)")
        if status >= 500:
            raise LikeAttemptError("server", f"X server error (HTTP {status})")


def _perform_like_attempt(session: _LikeSession, candidate: dict) -> str:
    page = session.new_page()
    http_errors: list[dict] = []
    phase = "navigation"

    def record_response(response):
        # Record endpoint paths only, never query strings, headers or cookies.
        path = urlsplit(response.url).path
        if response.status >= 400 and (
            response.request.resource_type == "document"
            or any(name in path for name in ("TweetDetail", "FavoriteTweet", "CreateFavorite"))
        ):
            http_errors.append({"path": path, "status": response.status})
            del http_errors[:-10]

    page.on("response", record_response)
    try:
        detail = _attach_tweet_detail_listener(page)
        target_url = candidate.get("like_target_url") or candidate["url"]
        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        _check_like_page(page, http_errors)
        _dismiss_cookie_prompt(page)
        tweet_id = str(candidate.get("like_target_id") or candidate["id"])
        if not candidate.get("like_target_id"):
            phase = "thread_resolution"
            payload = detail.get("payload")
            if payload is None:
                payload = _wait_for_tweet_detail(page, TWEET_DETAIL_WAIT_MS)
            if not any(
                str(item.get("rest_id")) == str(candidate["id"])
                for item in _iter_tweet_results(payload)
            ):
                raise LikeAttemptError(
                    "transient", "Tweet detail unavailable; thread target not resolved"
                )
            tweet_id, target_url = _resolve_like_target(candidate, payload)
            if tweet_id != str(candidate["id"]):
                print(f"   Thread target resolved: {target_url}")
                page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            candidate["like_target_id"] = tweet_id
            candidate["like_target_url"] = target_url
        phase = "exact_tweet"
        # Never fall back to another article (a reply or recommendation).
        article = page.locator(f"article:has(a[href$='/status/{tweet_id}'] time)").first
        article.wait_for(state="visible", timeout=30000)
        _check_like_page(page, http_errors)
        unlike = article.locator("[data-testid='unlike']")
        if unlike.count() and unlike.first.is_visible():
            return "already_liked"
        phase = "click"
        like = article.locator("[data-testid='like']")
        like.first.wait_for(state="visible", timeout=15000)
        # Persisted by the caller even if click or its confirmation times out.
        candidate["like_click_uncertain"] = True
        like.first.click()
        phase = "confirmation"
        unlike.first.wait_for(state="visible", timeout=20000)
        _check_like_page(page, http_errors)
        return "liked"
    except Exception as exc:
        try:
            _check_like_page(page, http_errors)
        except LikeAttemptError as classified:
            exc = classified
        except Exception:
            pass  # A closed page must not hide the original browser failure.
        diagnostic = {
            "phase": phase,
            "kind": _failure_kind(exc),
            "url": (page.url or "").split("?", 1)[0],
            "http_errors": http_errors,
            "recorded_at": _utc_now(),
        }
        with suppress(Exception):
            folder = session.state_path.parent / f"{session.state_path.stem}-diagnostics"
            folder.mkdir(parents=True, exist_ok=True)
            screenshot = folder / f"{candidate['id']}-{candidate.get('like_attempts', 0)}.png"
            page.screenshot(path=str(screenshot), timeout=5000)
            diagnostic["screenshot"] = str(screenshot)
        candidate["like_diagnostic"] = diagnostic
        raise exc
    finally:
        with suppress(Exception):
            page.close()


def apply_likes(
    state_path: Path,
    *,
    attempts_per_tweet: int = DEFAULT_LIKE_ATTEMPTS,
    max_consecutive_errors: int = 3,
    action_delay: float = 12,
    retry_delay: float = 30,
    cooldown: float = 180,
    recovery_rounds: int = 1,
) -> None:
    payload = _read_state(state_path)
    selected = sorted(
        _selected(payload),
        key=lambda candidate: candidate.get("rank", SELECTION_SIZE + 1),
        reverse=True,
    )
    if len(selected) != SELECTION_SIZE:
        raise RuntimeError(f"Weekly state must contain exactly {SELECTION_SIZE} selected tweets")
    if attempts_per_tweet < 1 or max_consecutive_errors < 1 or recovery_rounds < 0:
        raise ValueError("Attempt/error limits must be positive and recovery rounds nonnegative")
    if min(action_delay, retry_delay, cooldown) < 0:
        raise ValueError("Delays must be nonnegative")
    state = cfg.TWEET_LIKES_STATE.expanduser()
    if not state.exists():
        raise FileNotFoundError(f"storage_state not found at {state}")

    application = payload.setdefault("application", {})
    application.setdefault("started_at", _utc_now())
    application["status"] = "running"
    application.pop("failure_reason", None)
    application.pop("finished_at", None)
    hard_failure = False
    attempted = False
    with sync_playwright() as playwright:
        session = _LikeSession(playwright, state, state_path)
        try:
            # Honor an interrupted cooldown across separate invocations.
            if application.get("retry_not_before"):
                deadline = datetime.fromisoformat(application["retry_not_before"])
                _pause(max(0, (deadline - datetime.now(timezone.utc)).total_seconds()))
                application.pop("retry_not_before", None)
            for recovery in range(recovery_rounds + 1):
                consecutive_errors = 0
                for position, candidate in enumerate(selected, 1):
                    if candidate.get("like_status") in CONFIRMED_LIKE_STATUSES:
                        continue
                    for attempt in range(1, attempts_per_tweet + 1):
                        if attempted:
                            _pause(action_delay if attempt == 1 else retry_delay * 2 ** (attempt - 2))
                        attempted = True
                        print(
                            f"[{position:02d}/{len(selected)}] Rank {candidate.get('rank')} "
                            f"Like {candidate['url']} (attempt {attempt}/{attempts_per_tweet})",
                            flush=True,
                        )
                        candidate["like_attempts"] = int(candidate.get("like_attempts", 0)) + 1
                        candidate["last_like_attempt_at"] = _utc_now()
                        try:
                            candidate["like_status"] = _perform_like_attempt(session, candidate)
                            candidate["like_confirmed_at"] = _utc_now()
                            candidate.pop("like_error", None)
                            candidate.pop("like_error_kind", None)
                            candidate.pop("like_click_uncertain", None)
                            candidate.pop("like_diagnostic", None)
                        except Exception as exc:
                            kind = _failure_kind(exc)
                            candidate["like_status"] = (
                                "uncertain" if candidate.get("like_click_uncertain") else "failed"
                            )
                            candidate["like_error"] = str(exc)
                            candidate["like_error_kind"] = kind
                            hard_failure = kind == "authentication"
                            print(f"   {kind}: {exc}", flush=True)
                        _write_state(state_path, payload)
                        if hard_failure or candidate["like_status"] in CONFIRMED_LIKE_STATUSES:
                            break
                        # A 429 needs a cooldown, not an immediate same-tweet retry.
                        if candidate.get("like_error_kind") == "rate_limit":
                            break
                    if candidate["like_status"] in CONFIRMED_LIKE_STATUSES:
                        consecutive_errors = 0
                    else:
                        consecutive_errors += 1
                    if hard_failure or consecutive_errors >= max_consecutive_errors:
                        break
                    if candidate.get("like_error_kind") == "rate_limit":
                        break
                unresolved = [c for c in selected if c.get("like_status") not in CONFIRMED_LIKE_STATUSES]
                if not unresolved or hard_failure:
                    break
                if recovery < recovery_rounds:
                    application["retry_not_before"] = (
                        datetime.now(timezone.utc) + timedelta(seconds=cooldown * 2 ** recovery)
                    ).isoformat()
                    _write_state(state_path, payload)
                    print("Pausing before automatic recovery of unconfirmed Likes", flush=True)
                    # Refresh a potentially broken browser only after cooling down.
                    session.close()
                    _pause(cooldown * 2 ** recovery)
                    application.pop("retry_not_before", None)
        finally:
            session.close()

    confirmed = [c for c in selected if c.get("like_status") in CONFIRMED_LIKE_STATUSES]
    unresolved = [c for c in selected if c.get("like_status") not in CONFIRMED_LIKE_STATUSES]
    application.update(
        status="complete" if not unresolved else "failed",
        finished_at=_utc_now(),
        selected_count=len(selected),
        confirmed_count=len(confirmed),
        unresolved_count=len(unresolved),
    )
    if unresolved and not hard_failure:
        application["retry_not_before"] = (
            datetime.now(timezone.utc) + timedelta(seconds=cooldown)
        ).isoformat()
    if unresolved:
        application["failure_reason"] = (
            "Authentication or account challenge; manual session repair required"
            if hard_failure else "Recovery exhausted; unconfirmed Likes remain"
        )
    _write_state(state_path, payload)
    if unresolved:
        raise RuntimeError(f"{len(unresolved)} selected tweets remain without a confirmed Like")
    print(f"Confirmed {len(confirmed)} weekly Likes")


def status_payload(state_path: Path) -> dict:
    payload = _read_state(state_path)
    selected = _selected(payload)
    confirmed = [
        candidate for candidate in selected
        if candidate.get("like_status") in CONFIRMED_LIKE_STATUSES
    ]
    return {
        "week": payload.get("week"),
        "start": payload.get("start"),
        "end": payload.get("end"),
        "collection_status": payload.get("collection", {}).get("status"),
        "successful_handles": len(set(payload.get("completed_handles", []))),
        "failed_handles": len({
            error.get("handle") for error in payload.get("errors", [])
            if error.get("handle")
        }),
        "candidate_count": len(payload.get("candidates", [])),
        "review_pool_count": payload.get("review_pool_count", 0),
        "selected_count": len(selected),
        "confirmed_count": len(confirmed),
        "unresolved_count": len(selected) - len(confirmed),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    collect_parser = subparsers.add_parser("collect")
    collect_parser.add_argument("--start", help="Monday in YYYY-MM-DD format")
    collect_parser.add_argument("--max-per-handle", type=int, default=100)
    collect_parser.add_argument(
        "--attempts-per-handle", type=int, default=DEFAULT_COLLECTION_ATTEMPTS
    )
    select_parser = subparsers.add_parser("select")
    select_parser.add_argument("state", type=Path)
    select_parser.add_argument("selection", type=Path)
    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("state", type=Path)
    apply_parser.add_argument(
        "--attempts-per-tweet", type=int, default=DEFAULT_LIKE_ATTEMPTS
    )
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("state", type=Path)
    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--start", help="Monday in YYYY-MM-DD format")
    args = parser.parse_args()

    if args.command == "plan":
        start, end, week_id = _week_bounds(args.start)
        corpus = load_corpus()
        print(
            json.dumps(
                {
                    "week": week_id,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "state": str(_state_path(week_id)),
                    "corpus_count": len(corpus),
                    "corpus_path": str(_corpus_path()),
                    "selection_size": SELECTION_SIZE,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "collect":
        _, _, week_id = _week_bounds(args.start)
        state_path = _state_path(week_id)
        with _state_lock(state_path):
            collect_week(
                args.start,
                max_per_handle=args.max_per_handle,
                attempts_per_handle=args.attempts_per_handle,
            )
        return 0

    state_path = args.state
    with _state_lock(state_path):
        if args.command == "select":
            apply_selection(state_path, args.selection)
        elif args.command == "apply":
            apply_likes(state_path, attempts_per_tweet=args.attempts_per_tweet)
        elif args.command == "status":
            status = status_payload(state_path)
            print(json.dumps(status, ensure_ascii=False, indent=2))
            return 0 if (
                status["selected_count"] == SELECTION_SIZE
                and status["confirmed_count"] == SELECTION_SIZE
            ) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
