#!/usr/bin/env python3
"""Download Instapaper articles to HTML and Markdown without the rest of the repo."""
from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)
STAR_PREFIXES = ("⭐", "⭐️")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Descarga todos los artículos de Instapaper como HTML y Markdown."
    )
    parser.add_argument(
        "output_dir",
        type=Path,
        help="Directorio donde se guardarán los artículos descargados.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignora el registro local (.instapaper_downloads.txt) y fuerza la descarga.",
    )
    parser.add_argument(
        "--username",
        default=os.getenv("INSTAPAPER_USERNAME"),
        help="Usuario de Instapaper (por defecto INSTAPAPER_USERNAME).",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("INSTAPAPER_PASSWORD"),
        help="Contraseña de Instapaper (por defecto INSTAPAPER_PASSWORD).",
    )
    return parser.parse_args()


def _sanitize_title(name: str) -> str:
    safe = "".join(c for c in name if c.isalpha() or c.isdigit() or c == " ").strip()
    return re.sub(r"\s+", " ", safe)[:200]


def _has_star_prefix(title: str) -> bool:
    if not title:
        return False
    normalized = title.strip()
    return normalized.startswith(STAR_PREFIXES)


def _strip_star_prefix(title: str) -> str:
    if not title:
        return title
    return re.sub(r"^\s*(?:[\u2B50\u2605\u272A\u272D]\uFE0F?\s*)+", "", title).strip()


def _is_starred_from_title_only(html: str) -> bool:
    try:
        soup = BeautifulSoup(html, "html.parser")
        page_title = soup.title.string if (soup.title and soup.title.string) else ""
        return _has_star_prefix(page_title)
    except Exception:
        return False


def _truncate_filename(name: str, extension: str, max_length: int = 200) -> str:
    total_length = len(name) + len(extension) + 1
    if total_length > max_length:
        name = name[: max_length - len(extension) - 1]
    return name + extension


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    counter = 1
    while True:
        candidate = path.with_name(f"{stem} ({counter}){suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


@dataclass
class RegistryEntry:
    starred: bool
    timestamp: str


class DownloadRegistry:
    """Registro ligero para evitar descargas duplicadas entre ejecuciones."""

    def __init__(self, path: Path):
        self.path = path
        self.entries: Dict[str, RegistryEntry] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            parts = line.strip().split("\t")
            if len(parts) < 2:
                continue
            article_id, starred = parts[0], parts[1] == "1"
            timestamp = parts[2] if len(parts) > 2 else ""
            self.entries[article_id] = RegistryEntry(starred=starred, timestamp=timestamp)

    def should_skip(self, article_id: str, starred_hint: Optional[bool], force: bool) -> bool:
        if force:
            return False
        entry = self.entries.get(article_id)
        if not entry:
            return False
        if starred_hint is None:
            return True
        return entry.starred == starred_hint

    def mark(self, article_id: str, starred: bool) -> None:
        ts = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        self.entries[article_id] = RegistryEntry(starred=starred, timestamp=ts)
        lines = [
            f"{aid}\t{'1' if data.starred else '0'}\t{data.timestamp}"
            for aid, data in self.entries.items()
        ]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class InstapaperDownloader:
    def __init__(self, username: str, password: str, output_dir: Path):
        if not username or not password:
            raise ValueError("Configura usuario y contraseña de Instapaper.")
        self.username = username
        self.password = password
        self.output_dir = output_dir
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.registry = DownloadRegistry(self.output_dir / ".instapaper_downloads.txt")

    def download_all(self, *, force: bool = False) -> List[Path]:
        if not self._login():
            return []

        downloaded: List[Path] = []
        page = 1
        has_more = True
        while has_more:
            ids, has_more = self._get_article_ids(page)
            page += 1
            if not ids:
                break

            for article_id, starred_hint in ids:
                if self.registry.should_skip(article_id, starred_hint, force):
                    continue
                html_path, starred = self._download_article(article_id)
                md_path = self._html_to_markdown(html_path, starred)
                downloaded.extend([html_path, md_path])
                self.registry.mark(article_id, starred)

        return downloaded

    def _login(self) -> bool:
        resp = self.session.post(
            "https://www.instapaper.com/user/login",
            data={
                "username": self.username,
                "password": self.password,
                "keep_logged_in": "yes",
            },
            allow_redirects=True,
        )
        if resp.status_code >= 400:
            print(f"❌ Login fallido: HTTP {resp.status_code}")
            return False

        soup = BeautifulSoup(resp.text, "html.parser")
        if soup.find("form") and "login" in (soup.find("form").get("action") or ""):
            print("❌ Credenciales incorrectas de Instapaper")
            return False

        print("✅ Login en Instapaper correcto")
        return True

    def _get_article_ids(self, page: int) -> Tuple[List[Tuple[str, Optional[bool]]], bool]:
        url = f"https://www.instapaper.com/u/{page}"
        resp = self.session.get(url)
        soup = BeautifulSoup(resp.text, "html.parser")
        container = soup.find(id="article_list")
        if not container:
            return [], False

        items: List[Tuple[str, Optional[bool]]] = []
        for article in container.find_all("article"):
            aid = (article.get("id") or "").replace("article_", "")
            if not aid:
                continue
            items.append((aid, self._is_article_starred(article)))

        has_more = soup.find(class_="paginate_older") is not None
        return items, has_more

    def _is_article_starred(self, article_tag) -> Optional[bool]:
        classes = article_tag.get("class") or []
        if isinstance(classes, str):
            classes = [classes]
        classes = [cls.strip().lower() for cls in classes if cls]
        if "starred" in classes:
            return True
        data_starred = article_tag.get("data-starred")
        if isinstance(data_starred, str):
            normalized = data_starred.strip().lower()
            if normalized in {"1", "true", "yes"}:
                return True
            if normalized in {"0", "false", "no"}:
                return False
        return None

    def _download_article(self, article_id: str) -> Tuple[Path, bool]:
        resp = self.session.get(f"https://www.instapaper.com/read/{article_id}")
        soup = BeautifulSoup(resp.text, "html.parser")

        title_el = soup.find(id="titlebar").find("h1") if soup.find(id="titlebar") else None
        raw_title = title_el.getText() if title_el else (soup.title.string if soup.title else f"Instapaper {article_id}")
        title = _strip_star_prefix(raw_title) or f"Instapaper {article_id}"
        starred = _is_starred_from_title_only(resp.text)

        origin = soup.find(id="titlebar").find(class_="origin_line") if soup.find(id="titlebar") else None
        content_node = soup.find(id="story")
        content = content_node.decode_contents() if content_node else ""

        safe = _sanitize_title(title)
        if not safe:
            safe = f"Instapaper {article_id}"
        file_name = _truncate_filename(safe, ".html")
        html_path = _unique_path(self.output_dir / file_name)

        star_meta = '<meta name="instapaper-starred" content="true">\n' if starred else ""
        star_attr = ' data-instapaper-starred="true"' if starred else ""
        comment = "<!-- instapaper_starred: true method=read_or_list -->\n" if starred else ""
        origin_html = str(origin) if origin else ""
        html = (
            "<!DOCTYPE html>\n"
            f"{comment}"
            f"<html{star_attr}>\n<head>\n<meta charset=\"UTF-8\">\n"
            f"{star_meta}"
            f"<title>{title}</title>\n"
            "</head>\n<body>\n"
            f"<h1>{title}</h1>\n"
            f"<div id='origin'>{origin_html} · {article_id}</div>\n"
            f"{content}\n"
            "</body>\n</html>"
        )
        html_path.write_text(html, encoding="utf-8")
        print(f"📥 HTML guardado: {html_path.name}")
        return html_path, starred

    def _html_to_markdown(self, html_path: Path, starred: bool) -> Path:
        html_content = html_path.read_text(encoding="utf-8")
        markdown_body = md(html_content, heading_style="ATX")
        markdown_body = re.sub(
            r"^(#{1,6}\s*)(?:[\u2B50\u2605\u272A\u272D]\uFE0F?\s*)+",
            r"\1",
            markdown_body,
            flags=re.MULTILINE,
        )

        md_path = html_path.with_suffix(".md")
        if starred:
            markdown_body = f"---\ninstapaper_starred: true\n---\n\n{markdown_body}"
        md_path.write_text(markdown_body, encoding="utf-8")
        print(f"📝 Markdown guardado: {md_path.name}")
        return md_path


def main() -> None:
    args = parse_args()

    output_dir = args.output_dir.expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        downloader = InstapaperDownloader(
            username=args.username,
            password=args.password,
            output_dir=output_dir,
        )
    except ValueError as exc:
        print(f"❌ {exc}")
        raise SystemExit(1)

    files = downloader.download_all(force=args.force)
    if not files:
        print("⚠️  No se generaron archivos. Revisa las credenciales o si ya se descargó todo.")
        return

    html_count = sum(1 for f in files if f.suffix == ".html")
    print(f"✅ Descarga completada: {html_count} artículo(s) en {output_dir}")


if __name__ == "__main__":
    main()
