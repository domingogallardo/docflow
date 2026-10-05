"""Resolve weekly selections to downloaded files and reuse tweet consolidation."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import utils as U
from utils import build_daily_tweet_consolidated as builder
from utils.site_paths import raw_url_for_rel_path

SELECTION_SIZE = 50


def _mark_week(path: Path, week: str) -> None:
    original = path.read_text(encoding="utf-8")
    updated = U.upsert_front_matter(original, {"tweet_weekly_week": week})
    if updated != original:
        stat = path.stat()
        path.write_text(updated, encoding="utf-8")
        os.utime(path, (stat.st_atime, stat.st_mtime))


def consolidate_week(state_path: Path, base_dir: Path, *, dry_run: bool = False) -> bool:
    """Persist an exact file manifest; build only when every selected ID is resolved.

    Match the captured tweet ID or the known last tweet targeted by the Like.
    Body mentions and quoted tweet URLs never establish membership.
    """
    state = json.loads(state_path.read_text(encoding="utf-8"))
    week = state["week"]
    if not re.fullmatch(r"\d{4}-W\d{2}", week):
        raise ValueError("Invalid weekly selection name")
    selected = [c for c in state["candidates"] if c.get("selected")]
    if len(selected) != SELECTION_SIZE or len({c["id"] for c in selected}) != SELECTION_SIZE:
        raise ValueError(f"Weekly selection must contain {SELECTION_SIZE} unique tweets")
    if any(c.get("like_status") not in {"liked", "already_liked"} for c in selected):
        print(f"Weekly consolidation {week}: waiting for confirmed Likes")
        return False

    targets: set[str] = set()
    for candidate in selected:
        for tweet_id in {str(candidate["id"]), str(candidate.get("like_target_id") or candidate["id"])}:
            targets.add(tweet_id)

    start = datetime.fromisoformat(state["start"])
    end = datetime.fromisoformat(state["end"])
    years = {start.year, end.year}
    resolved: dict[str, str] = {}
    files: dict[Path, dict[str, str]] = {}
    captures: dict[str, tuple[Path, dict[str, str]]] = {}
    for family in ("Tweets", "Posts"):
        for year in sorted(years):
            for path in sorted((base_dir / family / f"{family} {year}").glob("*.md")):
                if path.name.startswith("Tweets "):
                    continue
                with path.open(encoding="utf-8", errors="replace") as stream:
                    meta, _ = U.split_front_matter(stream.read(8192))
                if meta.get("source") != "tweet" or meta.get("tweet_capture_source", "liked") != "liked":
                    continue
                tweet_id = meta.get("tweet_id", "")
                if not tweet_id:
                    match = re.search(r"/status/(\d+)", meta.get("tweet_url", ""))
                    tweet_id = match.group(1) if match else ""
                if tweet_id not in targets:
                    continue
                if tweet_id in captures:
                    raise ValueError(f"Multiple downloaded files match selected tweet {tweet_id}")
                captures[tweet_id] = (path, meta)

    for candidate in selected:
        member = str(candidate["id"])
        # Prefer the targeted full-thread capture over an earlier standalone tweet.
        capture = captures.get(str(candidate.get("like_target_id") or member)) or captures.get(member)
        if capture:
            path, meta = capture
            resolved[member] = path.relative_to(base_dir).as_posix()
            files[path] = meta

    missing = [str(c["id"]) for c in selected if str(c["id"]) not in resolved]
    if dry_run:
        print(json.dumps({"week": week, "selected_count": len(selected),
                          "resolved_count": len(resolved), "file_count": len(files),
                          "article_count": sum(builder._is_tweet_article(meta) for meta in files.values()),
                          "missing_ids": missing}, indent=2))
        return not missing
    # Reserve partial downloads too, so retries cannot move them into a daily file.
    for path, _ in captures.values():
        _mark_week(path, week)
    manifest_path = state_path.with_name(f"{week}-downloads.json")
    manifest = {"week": week, "selected_files": resolved, "missing_ids": missing,
                "status": "pending" if missing else "complete"}
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    tweets_dir = base_dir / "Tweets" / f"Tweets {start.year}"
    output_base = f"Tweets semana {week}"
    output_paths = [tweets_dir / f"{output_base}.{ext}" for ext in ("md", "html")]
    if not missing and manifest == previous and all(p.exists() for p in output_paths):
        return True
    if missing:
        print(f"Weekly consolidation {week}: waiting for {len(missing)} downloaded tweet(s)")
    else:
        regular = [p for p, meta in files.items() if not builder._is_tweet_article(meta)]
        articles = []
        for path, meta in files.items():
            if not builder._is_tweet_article(meta):
                continue
            entry = builder._build_entry(path)
            url = raw_url_for_rel_path(path.with_suffix(".html").relative_to(base_dir).as_posix())
            articles.append(builder.TweetEntry(
                path=path, title=entry.title, author_label=entry.author_label,
                kind="Artículo", tweet_url=entry.tweet_url, anchor_id=entry.anchor_id,
                body=f"[Leer artículo en Posts]({url})", mtime=entry.mtime,
            ))
        old_mtimes = {p: p.stat().st_mtime for p in output_paths if p.exists()}
        tweets_dir.mkdir(parents=True, exist_ok=True)
        builder.build_consolidated_from_files(
            tweets_dir, regular, day=f"{start.date()}–{(end - timedelta(days=1)).date()}",
            output_base=output_base, heading=output_base, additional_entries=articles,
        )
        for path, mtime in old_mtimes.items():
            builder._set_mtime(path, mtime)
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(manifest_path)
    return not missing


def consolidate_latest_week(base_dir: Path) -> None:
    """Resume the latest applied weekly batch after each normal tweet pipeline."""
    states = sorted((base_dir / "state" / "x_weekly").glob("????-W??.json"))
    if states:
        state = json.loads(states[-1].read_text())
        if state.get("application", {}).get("status") == "complete":
            consolidate_week(states[-1], base_dir)
