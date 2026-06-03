#!/usr/bin/env python3
"""Download web articles as Markdown through Obsidian Web Clipper.

This wrapper keeps Obsidian Web Clipper as the extraction engine and adds the
small amount of orchestration docflow needs when running outside the browser:
HTML download, lightweight output validation, selector fallbacks, and queue
input from Incoming/links.txt.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup

import config as cfg
import utils as U
from path_utils import unique_path
from openai_client import build_openai_client
from summary_ai import SummaryAIUpdater
from utils.backfill_original_article_dates import (
    ORIGINAL_PUBLISHED_AT_KEY,
    ORIGINAL_PUBLISHED_SOURCE_KEY,
    extract_original_published_date,
    extract_original_published_date_from_markdown,
)


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)
DEFAULT_CLIPPER_CLI = (
    Path(os.getenv("DOCFLOW_OBSIDIAN_CLIPPER_CLI", ""))
    if os.getenv("DOCFLOW_OBSIDIAN_CLIPPER_CLI")
    else Path.home() / "Repos-Github/obsidian-clipper/dist/cli.cjs"
)
URL_RE = re.compile(r"https?://[^\s<>\"]+")
DATA_IMAGE_RE = re.compile(r"data:image/[^)\s\"']+", re.IGNORECASE)
DEFAULT_NODE_BIN = Path("/opt/homebrew/bin/node")
ESCAPED_JSON_NOISE_RE = re.compile(r"\\n|\\/|\\u[0-9A-Fa-f]{4}")
HEADER_CHARSET_RE = re.compile(r"(?:^|;)\s*charset=[\"']?([^;\"'\s]+)", re.IGNORECASE)
HTML_CHARSET_RE = re.compile(
    rb"<meta[^>]+charset=[\"']?\s*([A-Za-z0-9._:-]+)",
    re.IGNORECASE,
)
HTML_HTTP_EQUIV_CHARSET_RE = re.compile(
    rb"<meta[^>]+http-equiv=[\"']?content-type[\"']?[^>]+content=[\"'][^\"']*charset=([^;\"'\s]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ClipAttempt:
    """A single Obsidian Clipper template strategy."""

    name: str
    content_format: str


@dataclass(frozen=True)
class DomainRule:
    """Selector fallbacks that are known to work for a domain family."""

    host_suffix: str
    attempts: tuple[ClipAttempt, ...]


@dataclass(frozen=True)
class MarkdownQuality:
    """Basic quality signals for a generated Markdown document."""

    usable: bool
    body_chars: int
    word_count: int
    data_image_count: int
    reason: str


@dataclass(frozen=True)
class ArticleDownloadResult:
    """Result of one URL-to-Markdown download."""

    url: str
    final_url: str
    output_path: Path
    attempt_name: str
    quality: MarkdownQuality
    removed_data_images: int


CONTENT_ATTEMPT = ClipAttempt("content", "{{content}}")

DOMAIN_RULES: tuple[DomainRule, ...] = (
    DomainRule(
        "esade.edu",
        (
            ClipAttempt(
                "esade-content-text",
                "{{selectorHtml:#featuredImageHero|markdown}}\n\n"
                "{{selectorHtml:.contentText|markdown}}",
            ),
        ),
    ),
    DomainRule(
        "substack.com",
        (
            ClipAttempt(
                "substack-body-markup",
                "{{selectorHtml:.body.markup|markdown}}",
            ),
        ),
    ),
    DomainRule(
        "lesswrong.com",
        (
            ClipAttempt(
                "lesswrong-post-content",
                "{{selectorHtml:.PostsPage-postContent|markdown}}",
            ),
        ),
    ),
    DomainRule(
        "marginalrevolution.com",
        (
            ClipAttempt(
                "marginalrevolution-entry-content",
                "{{selectorHtml:h1.entry-title|markdown}}\n\n"
                "{{selectorHtml:.byline|markdown}}\n\n"
                "{{selectorHtml:.entry-content|markdown}}",
            ),
        ),
    ),
    DomainRule(
        "thenewthings.com",
        (
            ClipAttempt(
                "beehiiv-content-blocks",
                "{{selectorHtml:#content-blocks|markdown}}",
            ),
        ),
    ),
)

GENERIC_SELECTOR_ATTEMPTS: tuple[ClipAttempt, ...] = (
    ClipAttempt("article", "{{selectorHtml:article|markdown}}"),
    ClipAttempt("main-article", "{{selectorHtml:main article|markdown}}"),
    ClipAttempt("main", "{{selectorHtml:main|markdown}}"),
    ClipAttempt("role-main", "{{selectorHtml:[role=\"main\"]|markdown}}"),
    ClipAttempt("entry-content", "{{selectorHtml:.entry-content|markdown}}"),
    ClipAttempt("post-content", "{{selectorHtml:.post-content|markdown}}"),
    ClipAttempt("article-content", "{{selectorHtml:.article-content|markdown}}"),
    ClipAttempt("content-text", "{{selectorHtml:.contentText|markdown}}"),
    ClipAttempt("body-markup", "{{selectorHtml:.body.markup|markdown}}"),
    ClipAttempt("body", "{{selectorHtml:body|markdown}}"),
)


def read_urls_from_file(path: Path) -> List[str]:
    """Read URLs from a plain text queue, ignoring blank lines and comments."""
    urls: List[str] = []
    if not path.exists():
        return urls

    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = URL_RE.search(line)
        if not match:
            continue
        urls.append(match.group(0).rstrip(").,;"))
    return dedupe_urls(urls)


def dedupe_urls(urls: Iterable[str]) -> List[str]:
    """Deduplicate URLs while preserving their first-seen order."""
    seen: set[str] = set()
    ordered: List[str] = []
    for raw_url in urls:
        url = raw_url.strip()
        if not url or url in seen:
            continue
        seen.add(url)
        ordered.append(url)
    return ordered


def attempts_for_url(url: str) -> List[ClipAttempt]:
    """Return extraction attempts in the order they should be tried."""
    host = (urlparse(url).hostname or "").lower()
    attempts: List[ClipAttempt] = [CONTENT_ATTEMPT]

    for rule in DOMAIN_RULES:
        suffix = rule.host_suffix.lower()
        if host == suffix or host.endswith("." + suffix):
            attempts.extend(rule.attempts)

    attempts.extend(GENERIC_SELECTOR_ATTEMPTS)

    unique: List[ClipAttempt] = []
    seen_names: set[str] = set()
    for attempt in attempts:
        if attempt.name in seen_names:
            continue
        seen_names.add(attempt.name)
        unique.append(attempt)
    return unique


def _html_bridge_redirect_url(html: str) -> str | None:
    """Return a client-side redirect URL from lightweight bridge pages."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    if title.startswith(("http://", "https://")):
        return title

    meta = soup.find("meta", attrs={"http-equiv": re.compile("^refresh$", re.I)})
    content = meta.get("content", "") if meta else ""
    match = re.search(r"url=([^;]+)$", content, flags=re.I)
    if match:
        target = unquote(match.group(1).strip().strip("'\""))
        if target.startswith(("http://", "https://")):
            return target
    return None


def _charset_from_content_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    match = HEADER_CHARSET_RE.search(content_type)
    return match.group(1).strip() if match else None


def _charset_from_html_bytes(content: bytes) -> str | None:
    head = content[:4096]
    for pattern in (HTML_CHARSET_RE, HTML_HTTP_EQUIV_CHARSET_RE):
        match = pattern.search(head)
        if match:
            return match.group(1).decode("ascii", errors="ignore").strip()
    return None


def _decode_html_response(response: requests.Response) -> str:
    """Decode HTML without treating requests' ISO-8859-1 default as declared."""
    encodings = [
        _charset_from_content_type(response.headers.get("content-type")),
        _charset_from_html_bytes(response.content),
        response.apparent_encoding,
        "utf-8",
    ]
    tried: set[str] = set()
    for encoding in encodings:
        if not encoding:
            continue
        normalized = encoding.lower()
        if normalized in tried:
            continue
        tried.add(normalized)
        try:
            return response.content.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return response.content.decode("utf-8", errors="replace")


def fetch_html(url: str, *, timeout: int = 30) -> tuple[str, str]:
    """Download page HTML with browser-like headers and return (html, final_url)."""
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    }
    current_url = url
    seen_urls: set[str] = set()
    for _ in range(3):
        response = requests.get(current_url, headers=headers, timeout=timeout)
        response.raise_for_status()
        html = _decode_html_response(response)

        bridge_url = _html_bridge_redirect_url(html)
        if not bridge_url or bridge_url in seen_urls:
            return html, response.url
        seen_urls.add(current_url)
        current_url = bridge_url

    return html, response.url


def clean_html_for_markdown(html: str, *, remove_data_images: bool = True) -> tuple[str, int]:
    """Apply minimal docflow-specific cleanup before handing HTML to Clipper."""
    if not remove_data_images:
        return html, 0

    soup = BeautifulSoup(html, "html.parser")
    removed = 0
    for img in soup.find_all("img"):
        src = img.get("src") or ""
        if src.startswith("data:image"):
            img.decompose()
            removed += 1
    return str(soup), removed


def build_template(attempt: ClipAttempt) -> dict:
    """Build a temporary Obsidian Clipper template for an attempt."""
    return {
        "noteNameFormat": "{{title}}",
        "noteContentFormat": attempt.content_format,
        "properties": [
            {"name": "source", "value": "{{url}}", "type": "text"},
        ],
    }


def resolve_node_bin(node_bin: str) -> str:
    """Resolve Node.js in cron-friendly locations as well as PATH."""
    expanded = Path(node_bin).expanduser()
    if expanded.parent != Path(".") and expanded.exists():
        return str(expanded)

    found = shutil.which(node_bin)
    if found:
        return found

    if node_bin == "node" and DEFAULT_NODE_BIN.exists():
        return str(DEFAULT_NODE_BIN)

    raise RuntimeError(f"Node.js executable not found: {node_bin}")


def run_clipper(
    *,
    clipper_cli: Path,
    node_bin: str,
    url: str,
    html_path: Path,
    template_path: Path,
    output_path: Path,
) -> None:
    """Run Obsidian Web Clipper CLI for one template attempt."""
    if not clipper_cli.exists():
        raise RuntimeError(f"Obsidian Clipper CLI not found: {clipper_cli}")
    resolved_node_bin = resolve_node_bin(node_bin)

    command = [
        resolved_node_bin,
        str(clipper_cli),
        url,
        "--template",
        str(template_path),
        "--html",
        str(html_path),
        "--output",
        str(output_path),
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"Obsidian Clipper failed for {url}: {detail}")


def markdown_quality(
    markdown: str,
    *,
    min_chars: int = 800,
    min_words: int = 120,
) -> MarkdownQuality:
    """Decide whether generated Markdown looks like article content."""
    body = strip_frontmatter(markdown).strip()
    body_chars = len(body)
    words = re.findall(r"\w+", body, flags=re.UNICODE)
    data_image_count = len(DATA_IMAGE_RE.findall(markdown))
    escaped_json_noise_count = len(ESCAPED_JSON_NOISE_RE.findall(body))

    if data_image_count:
        return MarkdownQuality(
            False,
            body_chars,
            len(words),
            data_image_count,
            "contains data:image payloads",
        )
    if body.startswith(("\\[", "[")) and escaped_json_noise_count >= 20:
        return MarkdownQuality(
            False,
            body_chars,
            len(words),
            0,
            "looks like escaped JSON instead of Markdown",
        )
    if "childrenIDs" in body and escaped_json_noise_count >= 20:
        return MarkdownQuality(
            False,
            body_chars,
            len(words),
            0,
            "contains escaped comment JSON",
        )
    if body_chars < min_chars:
        return MarkdownQuality(False, body_chars, len(words), 0, "body too short")
    if len(words) < min_words:
        return MarkdownQuality(False, body_chars, len(words), 0, "too few words")
    return MarkdownQuality(True, body_chars, len(words), 0, "ok")


def strip_frontmatter(markdown: str) -> str:
    """Remove leading YAML frontmatter if present."""
    lines = markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        return markdown
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[index + 1 :])
    return markdown


def original_published_metadata(html: str, markdown: str, *, url: str) -> dict[str, str]:
    """Return original publication metadata discovered during URL clipping."""
    candidate = (
        extract_original_published_date(html)
        or extract_original_published_date_from_markdown(markdown)
        or extract_original_published_date("", url=url)
    )
    if candidate is None:
        return {}
    return {
        ORIGINAL_PUBLISHED_AT_KEY: candidate.value,
        ORIGINAL_PUBLISHED_SOURCE_KEY: candidate.source,
    }


def default_output_path(output_dir: Path, url: str) -> Path:
    """Build a stable, docflow-friendly filename from the URL path."""
    parsed = urlparse(url)
    raw_slug = unquote(Path(parsed.path.rstrip("/") or parsed.hostname or "article").name)
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", raw_slug).strip("-._")
    if not slug:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", parsed.netloc).strip("-._") or "article"
    if len(slug) > 140:
        slug = slug[:140].rstrip("-._")
    return unique_path(output_dir / f"clipper-{slug}.md")


def download_url_to_markdown(
    url: str,
    *,
    output_dir: Path,
    output_path: Path | None = None,
    clipper_cli: Path = DEFAULT_CLIPPER_CLI,
    node_bin: str = "node",
    keep_html_dir: Path | None = None,
    remove_data_images: bool = True,
    min_chars: int = 800,
    min_words: int = 120,
    source_x_post_url: str | None = None,
) -> ArticleDownloadResult:
    """Download a URL and save a validated Markdown file."""
    html, final_url = fetch_html(url)
    cleaned_html, removed_data_images = clean_html_for_markdown(
        html,
        remove_data_images=remove_data_images,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_path or default_output_path(output_dir, final_url)
    destination.parent.mkdir(parents=True, exist_ok=True)

    last_quality: MarkdownQuality | None = None
    last_attempt_name = ""

    with tempfile.TemporaryDirectory(prefix="docflow-clipper-") as tmp:
        tmp_dir = Path(tmp)
        html_path = tmp_dir / "page.html"
        html_path.write_text(cleaned_html, encoding="utf-8")

        if keep_html_dir:
            keep_html_dir.mkdir(parents=True, exist_ok=True)
            keep_target = unique_path(keep_html_dir / (destination.stem + ".html"))
            keep_target.write_text(cleaned_html, encoding="utf-8")

        for attempt in attempts_for_url(final_url):
            template_path = tmp_dir / f"{attempt.name}.json"
            attempt_output = tmp_dir / f"{attempt.name}.md"
            template_path.write_text(
                json.dumps(build_template(attempt), ensure_ascii=False),
                encoding="utf-8",
            )
            run_clipper(
                clipper_cli=clipper_cli,
                node_bin=node_bin,
                url=final_url,
                html_path=html_path,
                template_path=template_path,
                output_path=attempt_output,
            )
            markdown = attempt_output.read_text(encoding="utf-8", errors="replace")
            quality = markdown_quality(
                markdown,
                min_chars=min_chars,
                min_words=min_words,
            )
            last_quality = quality
            last_attempt_name = attempt.name
            if quality.usable:
                extra_metadata = {
                    "docflow_extractor": "obsidian-clipper",
                    "docflow_extraction_attempt": attempt.name,
                    "docflow_final_url": final_url,
                    "docflow_removed_data_images": removed_data_images,
                }
                extra_metadata.update(
                    original_published_metadata(html, markdown, url=final_url)
                )
                if url.rstrip("/") != final_url.rstrip("/"):
                    extra_metadata["docflow_original_url"] = url
                if source_x_post_url and source_x_post_url.startswith(
                    ("http://", "https://")
                ):
                    extra_metadata["tweet_url"] = source_x_post_url
                markdown = U.enrich_markdown_metadata(
                    markdown,
                    source_url=final_url,
                    extra=extra_metadata,
                )
                markdown = SummaryAIUpdater(
                    build_openai_client(cfg.OPENAI_KEY)
                ).add_summary_to_markdown(markdown)
                destination.write_text(markdown, encoding="utf-8")
                return ArticleDownloadResult(
                    url=url,
                    final_url=final_url,
                    output_path=destination,
                    attempt_name=attempt.name,
                    quality=quality,
                    removed_data_images=removed_data_images,
                )

    raise RuntimeError(
        f"No usable Markdown extracted from {url}; "
        f"last attempt={last_attempt_name}, reason={last_quality.reason if last_quality else 'unknown'}"
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download web URLs as Markdown into docflow Incoming."
    )
    parser.add_argument("urls", nargs="*", help="URL(s) to download")
    parser.add_argument(
        "--links-file",
        type=Path,
        help=(
            "Plain text file with one or more URLs. Defaults to Incoming/links.txt "
            "when no URL is passed. This low-level command does not mutate the file."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=cfg.INCOMING,
        help="Directory where Markdown files are written. Defaults to BASE_DIR/Incoming.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output path for a single URL.",
    )
    parser.add_argument(
        "--clipper-cli",
        type=Path,
        default=DEFAULT_CLIPPER_CLI,
        help="Path to Obsidian Web Clipper dist/cli.cjs.",
    )
    parser.add_argument(
        "--node-bin",
        default=os.getenv("NODE_BIN", "node"),
        help="Node.js executable to run the clipper CLI.",
    )
    parser.add_argument(
        "--keep-html-dir",
        type=Path,
        help="Optional directory where cleaned HTML snapshots are kept for debugging.",
    )
    parser.add_argument(
        "--keep-data-images",
        action="store_true",
        help="Keep inline data:image payloads instead of removing them before conversion.",
    )
    parser.add_argument(
        "--min-chars",
        type=int,
        default=800,
        help="Minimum Markdown body characters required before accepting an attempt.",
    )
    parser.add_argument(
        "--min-words",
        type=int,
        default=120,
        help="Minimum Markdown body words required before accepting an attempt.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    urls = dedupe_urls(args.urls)
    output_dir = args.output_dir.expanduser()
    output_path = args.output.expanduser() if args.output else None
    keep_html_dir = args.keep_html_dir.expanduser() if args.keep_html_dir else None

    links_file = args.links_file
    if not urls:
        links_file = (links_file or cfg.INCOMING / "links.txt").expanduser()
        urls = read_urls_from_file(links_file)
        if not urls:
            print(f"No URLs found in {links_file}")
            return 0

    if args.output and len(urls) != 1:
        raise SystemExit("--output can only be used with a single URL")

    failures = 0
    for url in urls:
        try:
            result = download_url_to_markdown(
                url,
                output_dir=output_dir,
                output_path=output_path,
                clipper_cli=args.clipper_cli.expanduser(),
                node_bin=args.node_bin,
                keep_html_dir=keep_html_dir,
                remove_data_images=not args.keep_data_images,
                min_chars=args.min_chars,
                min_words=args.min_words,
            )
        except Exception as exc:
            failures += 1
            print(f"Error processing {url}: {exc}")
            continue

        print(
            "Saved Markdown: "
            f"{result.output_path} "
            f"(attempt={result.attempt_name}, "
            f"words={result.quality.word_count}, "
            f"removed_data_images={result.removed_data_images})"
        )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
