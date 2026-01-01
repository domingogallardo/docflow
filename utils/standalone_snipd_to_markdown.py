#!/usr/bin/env python3
"""
Standalone converter to generate clean Markdown files from a Snipd export.

Basic usage:
    python utils/standalone_snipd_to_markdown.py input.md --output-dir ./output

The command splits files with multiple episodes, cleans Snipd artifacts
(<details> blocks, audio links, <br/> breaks) and adds an index with anchors
for each snip under the "## Snips" section.
"""
from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path
from typing import Iterable, List

SNIP_INDEX_MARKER = "<!-- snip-index -->"


class SnipdMarkdownConverter:
    """Convert a Snipd Markdown export into clean Markdown files."""

    def __init__(self, input_file: Path, output_dir: Path):
        self.input_file = input_file
        self.output_dir = output_dir

        self.hr_pattern = re.compile(r"^\s*([\-*_]\s*){3,}$")
        self.summary_tag = re.compile(r"<summary>(.*?)</summary>", re.IGNORECASE | re.DOTALL)
        self.snip_link = re.compile(r"🎧\s*\[[^\]]*\]\((https://share\.snipd\.com/[^)]+)\)")
        self.h1_pattern = re.compile(r"^#\s+.+$", re.MULTILINE)

    def convert(self) -> List[Path]:
        """Process the input file and return generated paths."""
        if not self.input_file.exists():
            raise FileNotFoundError(f"Input file not found: {self.input_file}")

        raw_text = self.input_file.read_text(encoding="utf-8", errors="ignore")
        source = self._front_matter_source(raw_text)
        if source and source.lower() != "podcast":
            print("⚠️  Input already has a different source; skipping.")
            return []
        if source is None and not self._looks_like_podcast(raw_text):
            print("⚠️  Input does not look like a Snipd podcast export.")
            return []

        episodes = self._split_by_episode(raw_text)
        multiple = len(episodes) > 1

        self.output_dir.mkdir(parents=True, exist_ok=True)

        generated: list[Path] = []
        for index, episode_text in enumerate(episodes, start=1):
            episode_text = self._ensure_podcast_front_matter(episode_text)
            cleaned_text = self._clean_snipd_text(episode_text)
            cleaned_text = self._ensure_podcast_front_matter(cleaned_text)
            title = self._extract_episode_title_from_text(cleaned_text)
            if title:
                base = title
            elif multiple:
                base = f"{self.input_file.stem} - part {index}"
            else:
                base = self.input_file.stem
            filename = self._unique_filename(base)
            output_path = self.output_dir / filename
            output_path.write_text(cleaned_text, encoding="utf-8")
            generated.append(output_path)

        return generated

    def _split_by_episode(self, text: str) -> list[str]:
        """Split content into episodes using level-1 headings."""
        matches = list(self.h1_pattern.finditer(text))
        if len(matches) <= 1:
            return [text]

        starts = [m.start() for m in matches]
        ends = starts[1:] + [len(text)]
        return [text[s:e].lstrip() for s, e in zip(starts, ends)]

    def _clean_snipd_text(self, text: str) -> str:
        """Apply cleanup rules and add the snips index."""
        text = re.sub(r"<br\s*/?>\s*>\s*", "\n> ", text)
        text = re.sub(r"<br\s*/?>", "\n", text)
        text = self.snip_link.sub(self._replace_snip_link, text)
        text = self._lift_show_notes_section(text)
        cleaned_lines = self._clean_lines(text.splitlines(keepends=True))
        final_text = "".join(cleaned_lines)
        return self._add_snip_index(final_text)

    def _ensure_podcast_front_matter(self, text: str) -> str:
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            cleaned = text.lstrip("\n")
            return f"---\nsource: podcast\n---\n\n{cleaned}"

        for idx in range(1, len(lines)):
            if lines[idx].strip() != "---":
                continue
            front_lines = lines[1:idx]
            body_lines = lines[idx + 1 :]
            found_source = False
            updated = False
            new_front_lines: list[str] = []
            for line in front_lines:
                stripped = line.strip()
                if stripped.startswith("source:"):
                    found_source = True
                    if stripped != "source: podcast":
                        new_front_lines.append("source: podcast")
                        updated = True
                    else:
                        new_front_lines.append(line)
                    continue
                new_front_lines.append(line)

            if not found_source:
                new_front_lines.insert(0, "source: podcast")
                updated = True

            if not updated:
                return text

            rebuilt = "\n".join(["---", *new_front_lines, "---", *body_lines])
            if text.endswith("\n") and not rebuilt.endswith("\n"):
                rebuilt += "\n"
            return rebuilt

        cleaned = text.lstrip("\n")
        return f"---\nsource: podcast\n---\n\n{cleaned}"

    def _front_matter_source(self, text: str) -> str | None:
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            return None
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                for line in lines[1:idx]:
                    if ":" not in line:
                        continue
                    key, raw = line.split(":", 1)
                    if key.strip() == "source":
                        value = raw.strip()
                        if value.startswith(("\"", "'")) and value.endswith(("\"", "'")) and len(value) >= 2:
                            value = value[1:-1]
                        return value
                return None
        return None

    def _looks_like_podcast(self, text: str) -> bool:
        lowered = text.lower()
        return "episode metadata" in lowered and "## snips" in lowered

    def _replace_snip_link(self, match: re.Match[str]) -> str:
        url = match.group(1)
        return (
            f'<div style="text-align: center; margin: 10px 0;">\n'
            f'  <a href="{url}" target="_blank" rel="noopener" '
            f'style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); '
            f'color: white; padding: 12px 20px; text-decoration: none; border-radius: 25px; '
            f'font-size: 14px; font-weight: 500; box-shadow: 0 4px 15px rgba(0,0,0,0.2); '
            f'transition: all 0.3s ease;">\n'
            f'    🎧 Play audio clip\n'
            f'  </a>\n'
            f'</div>'
        )

    def _clean_lines(self, lines: Iterable[str]) -> list[str]:
        cleaned: list[str] = []
        for line in lines:
            lower = line.lower()
            stripped = line.strip()

            if "click to expand" in stripped.lower():
                continue

            if "<details" in lower or "</details>" in lower:
                continue

            if "<summary" in lower:
                cleaned_text = self.summary_tag.sub(r"\1", line).strip()
                if cleaned_text.lower() != "click to expand":
                    cleaned.append(cleaned_text + "\n")
                continue

            if self.hr_pattern.match(line):
                continue

            cleaned.append(line)
        return cleaned

    def _lift_show_notes_section(self, text: str) -> str:
        details_re = re.compile(
            r"<details>\s*<summary>(?P<title>.*?)</summary>(?P<body>.*?)</details>"
            r"(?P<trailing>(?:\s*\n- [^\n]+)*)",
            re.IGNORECASE | re.DOTALL,
        )

        def _repl(match: re.Match[str]) -> str:
            raw_title = match.group("title") or ""
            title = self.summary_tag.sub(r"\1", raw_title).strip() or "Show notes"

            body = (match.group("body") or "").strip()
            trailing = (match.group("trailing") or "").strip()

            parts: list[str] = []
            if trailing:
                parts.append(trailing)

            heading = f"## {title}\n\n{body}\n\n" if body else f"## {title}\n\n"
            parts.append(heading)

            return "\n\n".join(parts)

        return details_re.sub(_repl, text)

    def _add_snip_index(self, text: str) -> str:
        match = re.search(r"(##\s+Snips\s*(?:\r?\n)*)", text, flags=re.IGNORECASE)
        if not match:
            return text

        prefix = text[: match.end()]
        rest = text[match.end() :]

        next_section = re.search(r"\n##\s+", rest)
        snip_block = rest[: next_section.start()] if next_section else rest
        suffix = rest[next_section.start() :] if next_section else ""

        if SNIP_INDEX_MARKER in snip_block:
            return text

        heading_pattern = re.compile(
            r"^(?P<prefix>###\s+)(?P<title>.+?)(?P<attrs>\s*\{[^}]*\})?\s*$",
            re.MULTILINE,
        )

        headings: list[tuple[str, str]] = []

        def replace_heading(match: re.Match[str]) -> str:
            title = match.group("title").strip()
            if not title:
                return match.group(0)

            attr_text = match.group("attrs") or ""
            anchor = self._extract_anchor_id(attr_text)

            if not anchor:
                anchor = self._build_snip_anchor(title, len(headings) + 1)
                if attr_text:
                    inner = attr_text.strip()[1:-1].strip()
                    inner = f"{inner} " if inner else ""
                    attr_text = f" {{{inner}#{anchor}}}"
                else:
                    attr_text = f" {{#{anchor}}}"

            headings.append((title, anchor))
            return f"{match.group('prefix')}{title}{attr_text}"

        updated_block = heading_pattern.sub(replace_heading, snip_block)

        if not headings:
            return text

        index_lines = [f"- [{title}](#{anchor})" for title, anchor in headings if anchor]
        if not index_lines:
            return text

        index_block = f"{SNIP_INDEX_MARKER}\n" + "\n".join(index_lines) + "\n\n"
        return prefix + index_block + updated_block + suffix

    def _extract_anchor_id(self, attr_text: str | None) -> str | None:
        if not attr_text:
            return None
        match = re.search(r"#([A-Za-z0-9_-]+)", attr_text)
        return match.group(1) if match else None

    def _build_snip_anchor(self, title: str, index: int) -> str:
        slug = self._slugify(title)
        prefix = f"snip-{index:02d}"
        return f"{prefix}-{slug}" if slug else prefix

    def _slugify(self, text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text)
        ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        ascii_text = ascii_text.lower()
        ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text)
        return ascii_text.strip("-")

    def _extract_title(self, text: str) -> str | None:
        match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
        return match.group(1).strip() if match else None

    def _extract_episode_title_from_text(self, text: str) -> str | None:
        show_match = re.search(r"- Show:\s*(.+)", text)
        episode_match = re.search(r"- Episode title:\s*(.+)", text)

        if not episode_match:
            return None

        episode_title = episode_match.group(1).strip()
        show_name = show_match.group(1).strip() if show_match else None
        full_title = f"{show_name} - {episode_title}" if show_name else episode_title
        return self._sanitize_title_for_filename(full_title)

    def _sanitize_title_for_filename(self, title: str) -> str:
        cleaned = re.sub(r'[<>:"/\\|?*#]', '', title)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned[:200]

    def _unique_filename(self, title: str) -> str:
        base = self._sanitize_title_for_filename(title) or "podcast"
        filename = f"{base}.md"
        counter = 1
        while (self.output_dir / filename).exists():
            filename = f"{base} ({counter}).md"
            counter += 1
        return filename


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate ready-to-use Markdown files from a Snipd Markdown export. "
            "The command splits episodes, cleans artifacts, and adds a snips index "
            "with navigable anchors."
        )
    )
    parser.add_argument("input_file", type=Path, help="Markdown file exported from Snipd")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory where generated Markdown is saved (default: cwd)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    converter = SnipdMarkdownConverter(args.input_file, args.output_dir)
    generated = converter.convert()

    if generated:
        print("📻 Markdown generated:")
        for path in generated:
            print(f" - {path}")
    else:
        print("⚠️  No files were generated")


if __name__ == "__main__":
    main()
