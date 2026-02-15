"""Generate static tweet consolidated indexes under web/public/read/tweets.

Produces:
- read.html (years index)
- <YEAR>.html (consolidated entries for each year)

Source files are discovered from BASE_DIR/Tweets/Tweets <YEAR>/Consolidado Tweets *.html
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import os
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
BASE_DIR_ENV = "DOCFLOW_BASE_DIR"


@dataclass(frozen=True)
class TweetFile:
    name: str
    mtime: float


def fmt_date(ts: float) -> str:
    t = time.localtime(ts)
    return f"{t.tm_year}-{MONTHS[t.tm_mon-1]}-{t.tm_mday:02d} {t.tm_hour:02d}:{t.tm_min:02d}"


def resolve_base_dir(cli_base_dir: str | None) -> Path | None:
    if cli_base_dir:
        return Path(cli_base_dir).expanduser()

    env_value = os.getenv(BASE_DIR_ENV)
    if env_value:
        return Path(env_value).expanduser()

    try:
        from config import BASE_DIR  # local import for testability

        return Path(BASE_DIR)
    except Exception:
        pass

    try:
        repo_root = Path(__file__).resolve().parents[1]
        config_path = repo_root / "config.py"
        if not config_path.is_file():
            return None
        spec = importlib.util.spec_from_file_location("docflow_config", config_path)
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        assert spec and spec.loader
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        base_dir = getattr(module, "BASE_DIR", None)
        return Path(base_dir) if base_dir else None
    except Exception:
        return None


def discover_consolidated_by_year(base_dir: Path | None) -> dict[int, list[TweetFile]]:
    if base_dir is None:
        return {}

    tweets_root = base_dir / "Tweets"
    if not tweets_root.is_dir():
        return {}

    discovered: dict[int, list[TweetFile]] = {}
    for entry in tweets_root.iterdir():
        if not entry.is_dir() or not entry.name.startswith("Tweets "):
            continue
        suffix = entry.name[7:]
        if len(suffix) != 4 or not suffix.isdigit():
            continue

        year = int(suffix)
        items: list[TweetFile] = []
        for item in entry.iterdir():
            if not item.is_file():
                continue
            low_name = item.name.lower()
            if not item.name.startswith("Consolidado Tweets "):
                continue
            if not low_name.endswith((".html", ".htm")):
                continue
            items.append(TweetFile(name=item.name, mtime=item.stat().st_mtime))

        if items:
            items.sort(key=lambda it: it.mtime, reverse=True)
            discovered[year] = items

    return dict(sorted(discovered.items(), key=lambda kv: kv[0], reverse=True))


def render_years_html(index: dict[int, list[TweetFile]]) -> str:
    if not index:
        body = "<p>No consolidated tweets found.</p>"
    else:
        lines = ["<ul>"]
        for year in index:
            lines.append(f'<li><a href="{year}.html">{year}</a> ({len(index[year])})</li>')
        lines.append("</ul>")
        body = "\n".join(lines)

    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width">'
        '<script src="/read/article.js" defer></script>'
        '<title>Tweets</title></head><body>'
        '<h1>Tweets</h1>'
        f"{body}"
        '<p><a href="/read/">← Back to Read</a></p>'
        '</body></html>'
    )


def render_year_html(year: int, files: list[TweetFile]) -> str:
    if not files:
        list_html = "<p>No consolidated tweets found for this year.</p>"
    else:
        lines = ["<ul>"]
        for item in files:
            esc = html.escape(item.name)
            encoded_name = quote(item.name, safe="~!*()'")
            href = f"{year}/{encoded_name}"
            lines.append(f'<li><a href="{href}" title="{esc}">{esc}</a> — {fmt_date(item.mtime)}</li>')
        lines.append("</ul>")
        list_html = "\n".join(lines)

    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width">'
        '<script src="/read/article.js" defer></script>'
        f'<title>Tweets {year}</title></head><body>'
        f'<h1>Tweets {year}</h1>'
        f"{list_html}"
        '<p><a href="/read/tweets/read.html">← Back to Tweets</a></p>'
        '</body></html>'
    )


def write_indexes(output_dir: Path, index: dict[int, list[TweetFile]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    years_html = render_years_html(index)
    (output_dir / "read.html").write_text(years_html, encoding="utf-8")

    for year, files in index.items():
        (output_dir / f"{year}.html").write_text(render_year_html(year, files), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate static tweet consolidated indexes.")
    parser.add_argument("--base-dir", help="Base directory that contains Tweets/Tweets <YEAR> folders.")
    parser.add_argument(
        "--output-dir",
        default=str(Path("web") / "public" / "read" / "tweets"),
        help="Output directory for generated HTML indexes.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_dir = resolve_base_dir(args.base_dir)
    index = discover_consolidated_by_year(base_dir)

    output_dir = Path(args.output_dir)
    write_indexes(output_dir, index)
    print(f"✓ Generated tweet indexes in {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
