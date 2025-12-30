#!/usr/bin/env python3
"""Helpers to generate titles using OpenAI and rename Markdown/HTML pairs."""
from __future__ import annotations

import random
import re
import time
from pathlib import Path
from typing import Callable, Iterable, List, Optional

from path_utils import unique_pair

RenameFunc = Callable[[Path, str], Path]


class TitleAIUpdater:
    """Generate titles using OpenAI and rename associated Markdown/HTML files."""

    def __init__(
        self,
        ai_client,
        *,
        max_title_len: int = 250,
        num_words: int = 500,
        max_bytes_md: int = 1600,
        delay_seconds: float = 1.0,
        model: str = "gpt-5-mini",
    ) -> None:
        self.client = ai_client
        self.max_title_len = max_title_len
        self.num_words = num_words
        self.max_bytes_md = max_bytes_md
        self.delay_seconds = delay_seconds
        self.model = model

    # -------- public API --------
    def update_titles(self, candidates: Iterable[Path], rename_pair: RenameFunc) -> None:
        """Generate AI titles for the given Markdown files and rename them."""
        if self.client is None:
            print("🤖 AI client not configured; skipping title generation")
            return

        md_files = [
            Path(p) for p in candidates
            if Path(p).suffix.lower() == ".md"
        ]

        if not md_files:
            print("🤖 No new Markdown files to generate titles")
            return

        print(f"🤖 Generating titles for {len(md_files)} files...")

        for md_file in md_files:
            try:
                old_title, snippet = self._extract_content(md_file)
                lang = self._detect_language(" ".join(snippet.split()[:50]))
                new_title = self._generate_title(snippet, lang, old_title)
                print(f"📄 {old_title} → {new_title} [{lang}]")

                md_final = rename_pair(md_file, new_title)
                time.sleep(self.delay_seconds)

            except Exception as exc:  # pragma: no cover - logs for manual tracking
                print(f"❌ Error generating title for {md_file}: {exc}")

        print("🤖 Titles updated ✅")

    # -------- internals --------
    def _extract_content(self, path: Path) -> tuple[str, str]:
        raw_name = path.stem[: self.max_title_len]
        words: List[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                words.extend(line.strip().split())
                if len(words) >= self.num_words:
                    break
        snippet = " ".join(words[: self.num_words]).encode("utf-8")[: self.max_bytes_md].decode("utf-8", "ignore")
        return raw_name, snippet

    def _ai_text(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int,
        retries: int = 6,
    ) -> str:
        delay = 1.0
        last_err: Optional[Exception] = None

        for attempt in range(1, retries + 1):
            try:
                if self.client is None:
                    raise RuntimeError("AI client not configured")

                client = self.client
                if hasattr(client, "with_options"):
                    client = client.with_options(timeout=30)
                resp = client.responses.create(
                    model=self.model,
                    instructions=system,
                    input=prompt,
                    max_output_tokens=max_tokens,
                    reasoning={"effort": "minimal"},
                    text={"verbosity": "low"},
                )

                text = (getattr(resp, "output_text", "") or "").strip()
                if text:
                    return text

                outputs = getattr(resp, "output", None) or getattr(resp, "content", None)

                def _collect(value: object) -> str:
                    if value is None:
                        return ""
                    if isinstance(value, str):
                        return value
                    if isinstance(value, list):
                        return "".join(_collect(item) for item in value)
                    if isinstance(value, dict):
                        return "".join(
                            [
                                str(value.get("text", "")),
                                _collect(value.get("content")),
                                str(value.get("output_text", "")),
                            ]
                        )
                    if hasattr(value, "text"):
                        return str(getattr(value, "text", ""))
                    if hasattr(value, "content"):
                        return _collect(getattr(value, "content"))
                    if hasattr(value, "output_text"):
                        return str(getattr(value, "output_text", ""))
                    return str(value)

                if outputs:
                    text = _collect(outputs).strip()
                    if text:
                        return text

                messages = getattr(resp, "messages", None)
                if messages:
                    text = _collect(messages).strip()
                    if text:
                        return text

                try:
                    debug_payload = resp.model_dump() if hasattr(resp, "model_dump") else repr(resp)
                    print(f"🛠️ DEBUG empty OpenAI response: {debug_payload}")
                except Exception as debug_exc:
                    print(f"🛠️ DEBUG could not dump response: {debug_exc!r}")
                raise RuntimeError("Empty OpenAI response")
            except Exception as err:  # pragma: no cover - depende de red
                last_err = err
                status = (
                    getattr(err, "status_code", None)
                    or getattr(err, "http_status", None)
                    or getattr(getattr(err, "response", None), "status_code", None)
                )
                msg = str(err).lower()
                transient = (
                    (isinstance(status, int) and status in (429, 500, 502, 503, 504, 529))
                    or "overloaded" in msg
                    or "timeout" in msg
                    or "temporarily unavailable" in msg
                    or "rate limit" in msg
                )
                if attempt < retries and transient:
                    time.sleep(delay + random.uniform(0, 0.5))
                    delay = min(delay * 2, 20)
                    continue
                raise

        if last_err:
            raise last_err
        raise RuntimeError("Unknown failure in title generation")

    def _detect_language(self, sample_text: str) -> str:
        system = "Respond EXACTLY one word: 'Spanish' or 'English'. No quotes, no punctuation."
        prompt = (
            "Identify the language of the following text (Spanish or English):\n\n"
            f"{sample_text}\n\nLanguage:"
        )
        try:
            resp = self._ai_text(system=system, prompt=prompt, max_tokens=8)
            lowered = resp.strip().lower()
            if "spanish" in lowered or "español" in lowered or "espanol" in lowered:
                return "Spanish"
            if "english" in lowered or "inglés" in lowered or "ingles" in lowered:
                return "English"
        except Exception:
            pass

        if re.search(r"[áéíóúñ¿¡]", sample_text, re.I):
            return "Spanish"
        return "English"

    def _generate_title(self, snippet: str, lang: str, original_title: str) -> str:
        system = (
            "Return ONLY a single-line title and nothing else. "
            f"Write it in {lang}. "
            "If you detect the author, newsletter, or site/repo name, "
            "put it at the start and separate it with a dash. "
            f"Max {self.max_title_len} characters."
        )
        prompt = (
            "Generate an attractive title for the following content.\n\n"
            f"Original filename title: {original_title}\n\n"
            f"Content:\n{snippet}\n\nTitle:"
        )
        resp = self._ai_text(system=system, prompt=prompt, max_tokens=64)
        title = (
            resp.replace('"', "")
            .replace("#", "")
            .replace("“", "")
            .replace("”", "")
            .replace("‘", "")
            .replace("’", "")
            .strip()
        )
        for bad in [":", ".", "/"]:
            title = title.replace(bad, "-")
        title = re.sub(r"\s+", " ", title).strip()

        if "Tweet" in original_title and "Tweet" not in title:
            title = f"Tweet - {title}" if title else "Tweet -"

        return title[: self.max_title_len]


def rename_markdown_pair(md_path: Path, new_title: str) -> Path:
    """Rename a Markdown/HTML pair using the new title and return the MD path."""
    parent = md_path.parent
    base = _safe_filename(new_title)

    md_new = parent / f"{base}.md"
    html_old = md_path.with_suffix(".html")
    html_new = parent / f"{base}.html"
    md_new, html_new = unique_pair(
        md_new,
        html_new,
        allow_existing_primary=md_path,
        allow_existing_secondary=html_old,
    )

    if md_new != md_path:
        md_path.rename(md_new)
    if html_old.exists() and html_new != html_old:
        html_old.rename(html_new)

    return md_new


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*#]', '', name).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned[:240] or "markdown"
    return cleaned
