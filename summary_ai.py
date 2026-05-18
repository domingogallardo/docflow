#!/usr/bin/env python3
"""Helpers to generate Spanish summaries for Markdown front matter."""
from __future__ import annotations

import re
import time
from pathlib import Path

import utils as U
from title_ai import TitleAIUpdater


class SummaryAIUpdater:
    """Generate concise Spanish summaries and store them in docflow_summary."""

    def __init__(
        self,
        ai_client,
        *,
        model: str = "gpt-5-mini",
        num_words: int = 1200,
        max_bytes_md: int = 5000,
        max_summary_chars: int = 500,
        delay_seconds: float = 1.0,
    ) -> None:
        self.client = ai_client
        self.model = model
        self.num_words = num_words
        self.max_bytes_md = max_bytes_md
        self.max_summary_chars = max_summary_chars
        self.delay_seconds = delay_seconds
        self._ai = TitleAIUpdater(ai_client, model=model, delay_seconds=delay_seconds)

    def add_summary_to_file(self, md_path: Path, *, skip_tweets: bool = True) -> bool:
        """Add docflow_summary to a Markdown file when it is missing."""
        if self.client is None:
            return False

        if not md_path.exists() or md_path.suffix.lower() != ".md":
            return False

        original = md_path.read_text(encoding="utf-8", errors="replace")
        updated = self.add_summary_to_markdown(original, skip_tweets=skip_tweets)
        if updated == original:
            return False

        md_path.write_text(updated, encoding="utf-8")
        time.sleep(self.delay_seconds)
        return True

    def add_summary_to_markdown(self, md_text: str, *, skip_tweets: bool = True) -> str:
        """Return Markdown with a generated docflow_summary when appropriate."""
        if self.client is None:
            return md_text

        meta, body = U.split_front_matter(md_text)
        if skip_tweets and str(meta.get("source", "")).strip().lower() == "tweet":
            return md_text
        if str(meta.get("docflow_summary", "")).strip():
            return md_text

        snippet = self._snippet(body)
        if not snippet:
            return md_text

        summary = self._generate_summary(snippet)
        if not summary:
            return md_text

        return U.upsert_front_matter(md_text, {"docflow_summary": summary})

    def _snippet(self, body: str) -> str:
        cleaned_lines: list[str] = []
        in_fence = False

        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith(("```", "~~~")):
                in_fence = not in_fence
                continue
            if in_fence or not stripped:
                continue
            if stripped.startswith(("![", "[![")):
                continue
            if stripped.lower().startswith(("original link:", "http://", "https://")):
                continue
            cleaned_lines.append(stripped)

        words = " ".join(cleaned_lines).split()
        return " ".join(words[: self.num_words]).encode("utf-8")[: self.max_bytes_md].decode(
            "utf-8",
            "ignore",
        )

    def _generate_summary(self, snippet: str) -> str:
        system = (
            "Escribe SOLO un resumen en español, sin título ni viñetas. "
            "Debe tener entre 3 y 5 frases, capturar la idea central del texto "
            f"y no superar {self.max_summary_chars} caracteres."
        )
        prompt = (
            "Resume este contenido para el frontmatter de un archivo Markdown. "
            "Evita fórmulas como 'el artículo trata de' si puedes ser más directo.\n\n"
            f"{snippet}\n\nResumen:"
        )
        response = self._ai._ai_text(system=system, prompt=prompt, max_tokens=180)
        return self._normalize_summary(response)

    def _normalize_summary(self, summary: str) -> str:
        text = summary.replace("\n", " ")
        text = re.sub(r"\s+", " ", text).strip().strip('"“”')
        if len(text) <= self.max_summary_chars:
            return text

        clipped = text[: self.max_summary_chars].rstrip()
        sentence_end = max(clipped.rfind("."), clipped.rfind("!"), clipped.rfind("?"))
        if sentence_end >= 120:
            return clipped[: sentence_end + 1].strip()

        word_end = clipped.rfind(" ")
        if word_end >= 120:
            return clipped[:word_end].rstrip(" ,;:") + "."
        return clipped.rstrip(" ,;:") + "."
