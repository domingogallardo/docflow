from __future__ import annotations

import builtins
from pathlib import Path

from utils import build_tweets_index as mod


def _write_consolidated(path: Path, content: str, mtime: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    import os

    os.utime(path, (mtime, mtime))


def test_discover_consolidated_by_year_sorts_desc(tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    y2026 = base_dir / "Tweets" / "Tweets 2026"
    y2026.mkdir(parents=True)

    older = y2026 / "Consolidado Tweets 2026-01-01.html"
    newer = y2026 / "Consolidado Tweets 2026-01-02.html"
    _write_consolidated(older, "old", 1_000)
    _write_consolidated(newer, "new", 2_000)

    index = mod.discover_consolidated_by_year(base_dir)

    assert list(index.keys()) == [2026]
    assert [f.name for f in index[2026]] == [newer.name, older.name]


def test_write_indexes_generates_root_and_year_pages(tmp_path: Path) -> None:
    output = tmp_path / "out"
    index = {
        2026: [
            mod.TweetFile(name="Consolidado Tweets 2026-01-02.html", mtime=2_000, tweet_count=12),
            mod.TweetFile(name="Consolidado Tweets 2026-01-01.html", mtime=1_000, tweet_count=1),
        ],
        2025: [
            mod.TweetFile(name="Consolidado Tweets 2025-12-31.html", mtime=500, tweet_count=5),
        ],
    }

    mod.write_indexes(output, index)

    root = (output / "read.html").read_text(encoding="utf-8")
    y2026 = (output / "2026.html").read_text(encoding="utf-8")

    assert '<a href="2026.html">2026</a> (2)' in root
    assert '<a href="2025.html">2025</a> (1)' in root
    assert 'href="2026/Consolidado%20Tweets%202026-01-02.html"' in y2026
    assert 'href="2026/Consolidado%20Tweets%202026-01-01.html"' in y2026
    assert "(12 tweets)" in y2026
    assert "(1 tweet)" in y2026
    assert " — " not in y2026


def test_extract_tweet_count_from_summary_block(tmp_path: Path) -> None:
    html_path = tmp_path / "Consolidado Tweets 2026-02-13.html"
    html_path.write_text(
        "<ul><li>Total de ficheros: <strong>54</strong></li></ul>",
        encoding="utf-8",
    )

    assert mod._extract_tweet_count(html_path) == 54


def test_extract_tweet_count_falls_back_to_entry_articles(tmp_path: Path) -> None:
    html_path = tmp_path / "Consolidado Tweets 2026-02-13.html"
    html_path.write_text(
        '<article class="dg-entry"></article>'
        '<article class="card dg-entry extra"></article>'
        '<article class="other"></article>',
        encoding="utf-8",
    )

    assert mod._extract_tweet_count(html_path) == 2


def test_resolve_base_dir_prefers_cli(tmp_path: Path, monkeypatch) -> None:
    cli_base = tmp_path / "cli"
    cli_base.mkdir()
    monkeypatch.setenv(mod.BASE_DIR_ENV, str(tmp_path / "env"))

    resolved = mod.resolve_base_dir(str(cli_base))

    assert resolved == cli_base


def test_resolve_base_dir_falls_back_to_repo_config(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    utils_dir = repo_root / "utils"
    utils_dir.mkdir(parents=True)
    (repo_root / "config.py").write_text('BASE_DIR = "/tmp/fallback-base"\n', encoding="utf-8")
    fake_module_path = utils_dir / "build_tweets_index.py"
    fake_module_path.write_text("# test placeholder\n", encoding="utf-8")

    monkeypatch.delenv(mod.BASE_DIR_ENV, raising=False)
    monkeypatch.setattr(mod, "__file__", str(fake_module_path))

    original_import = builtins.__import__

    def patched_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "config":
            raise ImportError("forced import failure")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", patched_import)

    resolved = mod.resolve_base_dir(None)

    assert resolved == Path("/tmp/fallback-base")
