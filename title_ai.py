#!/usr/bin/env python3
"""Helpers para generar títulos usando Anthropic y renombrar pares Markdown/HTML."""
from __future__ import annotations

import random
import re
import time
from pathlib import Path
from typing import Callable, Iterable, List, Optional


RenameFunc = Callable[[Path, str], Path]


class TitleAIUpdater:
    """Genera títulos usando Anthropic y renombra archivos Markdown/HTML asociados."""

    def __init__(
        self,
        anthropic_client,
        done_file: Path,
        *,
        max_title_len: int = 250,
        num_words: int = 500,
        max_bytes_md: int = 1600,
        delay_seconds: float = 1.0,
    ) -> None:
        self.client = anthropic_client
        self.done_file = done_file
        self.max_title_len = max_title_len
        self.num_words = num_words
        self.max_bytes_md = max_bytes_md
        self.delay_seconds = delay_seconds

    # -------- public API --------
    def update_titles(self, candidates: Iterable[Path], rename_pair: RenameFunc) -> None:
        """Genera títulos IA para los Markdown indicados y los renombra."""
        if self.client is None:
            print("🤖 Cliente de IA no configurado; se omite la generación de títulos")
            return

        done = self._load_done_titles()
        md_files = [
            Path(p) for p in candidates
            if p.suffix.lower() == ".md" and str(p) not in done
        ]

        if not md_files:
            print("🤖 No hay Markdown nuevos para generar títulos")
            return

        print(f"🤖 Generando títulos para {len(md_files)} archivos...")

        for md_file in md_files:
            try:
                old_title, snippet = self._extract_content(md_file)
                lang = self._detect_language(" ".join(snippet.split()[:20]))
                new_title = self._generate_title(snippet, lang)
                print(f"📄 {old_title} → {new_title} [{lang}]")

                md_final = rename_pair(md_file, new_title)
                self._mark_title_done(md_final)
                time.sleep(self.delay_seconds)

            except Exception as exc:  # pragma: no cover - logs para seguimiento manual
                print(f"❌ Error generando título para {md_file}: {exc}")

        print("🤖 Títulos actualizados ✅")

    # -------- internals --------
    def _load_done_titles(self) -> set[str]:
        if self.done_file.exists():
            return set(self.done_file.read_text(encoding="utf-8").splitlines())
        return set()

    def _mark_title_done(self, path: Path) -> None:
        with self.done_file.open("a", encoding="utf-8") as fh:
            fh.write(str(path) + "\n")

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

    def _anthropic_text(self, *, system: str, prompt: str, max_tokens: int, retries: int = 6) -> str:
        delay = 1.0
        last_err: Optional[Exception] = None

        for attempt in range(1, retries + 1):
            try:
                resp = self.client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                    timeout=30,
                )
                parts: List[str] = []
                for block in getattr(resp, "content", []) or []:
                    block_type = getattr(block, "type", None)
                    if block_type == "text":
                        parts.append(getattr(block, "text", "") or "")
                    elif hasattr(block, "text"):
                        parts.append(getattr(block, "text", "") or "")
                    elif isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", ""))
                text = "".join(parts).strip()
                if not text:
                    content = getattr(resp, "content", None)
                    if content:
                        first = content[0]
                        text = str(getattr(first, "text", "") or "").strip()
                if not text:
                    raise RuntimeError("Respuesta vacía de Anthropic")
                return text
            except Exception as err:  # pragma: no cover - depende de red
                last_err = err
                status = getattr(err, "status_code", None) or getattr(getattr(err, "response", None), "status_code", None)
                msg = str(err).lower()
                transient = (
                    (isinstance(status, int) and status in (429, 500, 502, 503, 504, 529))
                    or "overloaded" in msg
                    or "timeout" in msg
                    or "temporarily unavailable" in msg
                )
                if attempt < retries and transient:
                    time.sleep(delay + random.uniform(0, 0.5))
                    delay = min(delay * 2, 20)
                    continue
                raise

        if last_err:
            raise last_err
        raise RuntimeError("Fallo desconocido en la generación de títulos")

    def _detect_language(self, text20: str) -> str:
        system = "Responde EXACTAMENTE una palabra: 'español' o 'inglés'. Sin comillas, sin puntuación."
        prompt = f"Indica el idioma del siguiente texto (español o inglés):\n\n{text20}\n\nIdioma:"
        try:
            resp = self._anthropic_text(system=system, prompt=prompt, max_tokens=3)
            lowered = resp.strip().lower()
            if "español" in lowered or "espanol" in lowered:
                return "español"
            if "inglés" in lowered or "ingles" in lowered or "english" in lowered:
                return "inglés"
        except Exception:
            pass

        if re.search(r"[áéíóúñ¿¡]", text20, re.I):
            return "español"
        return "inglés"

    def _generate_title(self, snippet: str, lang: str) -> str:
        system = (
            f"Devuelve SOLO un título en una línea y nada más. "
            f"Escríbelo en {lang}. "
            "Si detectas el nombre de la newsletter, del autor o del repositorio/sitio, "
            "ponlo al inicio y sepáralo con un guion. "
            f"Máx {self.max_title_len} caracteres."
        )
        prompt = (
            "Genera un título atractivo para el siguiente contenido.\n\n"
            f"Contenido:\n{snippet}\n\nTítulo:"
        )
        resp = self._anthropic_text(system=system, prompt=prompt, max_tokens=64)
        title = resp.replace('"', '').replace('#', '').strip()
        for bad in [":", ".", "/"]:
            title = title.replace(bad, "-")
        return re.sub(r"\s+", " ", title)[: self.max_title_len]


def rename_markdown_pair(md_path: Path, new_title: str) -> Path:
    """Renombra un par Markdown/HTML usando el nuevo título y devuelve la ruta MD."""
    parent = md_path.parent
    base = _safe_filename(new_title)

    md_new = parent / f"{base}.md"
    html_old = md_path.with_suffix(".html")
    html_new = parent / f"{base}.html"

    counter = 1
    while (md_new.exists() and md_new != md_path) or (html_new.exists() and html_new != html_old):
        md_new = parent / f"{base} ({counter}).md"
        html_new = parent / f"{base} ({counter}).html"
        counter += 1

    md_path.rename(md_new)
    if html_old.exists():
        html_old.rename(html_new)

    return md_new


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*#]', '', name).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned[:240] or "markdown"
    return cleaned
