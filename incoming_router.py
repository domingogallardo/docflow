#!/usr/bin/env python3
"""Classify Incoming/ files by document type for pipeline routing."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import utils as U
from image_processor import ImageProcessor


@dataclass
class IncomingPlan:
    """Buckets for Incoming/ classification."""
    tweet_markdown: list[Path] = field(default_factory=list)
    tweet_html: list[Path] = field(default_factory=list)
    instapaper_markdown: list[Path] = field(default_factory=list)
    instapaper_html: list[Path] = field(default_factory=list)
    podcast_markdown: list[Path] = field(default_factory=list)
    generic_markdown: list[Path] = field(default_factory=list)
    pdfs: list[Path] = field(default_factory=list)
    images: list[Path] = field(default_factory=list)


class IncomingRouter:
    """Lightweight router that classifies files in a single Incoming/ folder."""

    def __init__(self, incoming_dir: Path):
        self.incoming_dir = Path(incoming_dir)

    def build_plan(self) -> IncomingPlan:
        plan = IncomingPlan()

        plan.pdfs = U.list_files({".pdf"}, root=self.incoming_dir)
        plan.images = U.list_files(ImageProcessor.SUPPORTED_EXTS, root=self.incoming_dir)

        html_files = list(U.iter_html_files(self.incoming_dir))
        instapaper_html = set()
        tweet_html = set()

        for html_path in html_files:
            if self._is_instapaper_html(html_path):
                plan.instapaper_html.append(html_path)
                instapaper_html.add(html_path)
                continue
            if self._is_tweet_html(html_path):
                plan.tweet_html.append(html_path)
                tweet_html.add(html_path)

        md_files = list(self.incoming_dir.rglob("*.md"))
        instapaper_html_stems = {p.with_suffix("").name for p in instapaper_html}

        for md_path in md_files:
            if U.is_podcast_file(md_path):
                plan.podcast_markdown.append(md_path)
                continue
            if self._is_tweet_markdown(md_path):
                plan.tweet_markdown.append(md_path)
                continue
            if self._is_instapaper_markdown(md_path, instapaper_html_stems):
                plan.instapaper_markdown.append(md_path)
                continue
            plan.generic_markdown.append(md_path)

        return plan

    def _is_instapaper_markdown(self, path: Path, instapaper_html_stems: Iterable[str]) -> bool:
        html_path = path.with_suffix(".html")
        if html_path.exists():
            if html_path.with_suffix("").name in instapaper_html_stems:
                return True
            return self._is_instapaper_html(html_path)
        head = self._read_head(path)
        return "instapaper_starred:" in head

    def _is_instapaper_html(self, path: Path) -> bool:
        content = self._read_head(path)
        return "<div id='origin'>" in content or '<div id="origin"' in content

    def _is_tweet_markdown(self, path: Path) -> bool:
        lines = self._read_lines(path, 12)
        if not lines:
            return False
        header = lines[0].lower()
        if header.startswith("# tweet by") or header.startswith("# tweet de"):
            return True
        for line in lines[:5]:
            lower = line.lower()
            if ("view on x" in lower or "ver en x" in lower) and "x.com/" in lower:
                return True
        return False

    def _is_tweet_html(self, path: Path) -> bool:
        content = self._read_head(path)
        lowered = content.lower()
        if "tweet by" in lowered or "tweet de" in lowered:
            if "view on x" in lowered or "ver en x" in lowered:
                return True
        return False

    @staticmethod
    def _read_head(path: Path, max_bytes: int = 8192) -> str:
        try:
            with open(path, "rb") as fh:
                data = fh.read(max_bytes)
            return data.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    @staticmethod
    def _read_lines(path: Path, max_lines: int) -> list[str]:
        try:
            lines = []
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                for _ in range(max_lines):
                    line = fh.readline()
                    if not line:
                        break
                    stripped = line.strip()
                    if stripped:
                        lines.append(stripped)
            return lines
        except Exception:
            return []
