#!/usr/bin/env python3
"""
PodcastProcessor - unified module for full processing of Snipd podcasts.
"""
from __future__ import annotations
import re
import unicodedata
from pathlib import Path
from typing import List, Iterable

import utils as U


SNIP_INDEX_MARKER = "<!-- snip-index -->"


class PodcastProcessor:
    """Unified processor for the full Snipd podcasts pipeline."""
    
    def __init__(self, incoming_dir: Path, destination_dir: Path):
        self.incoming_dir = incoming_dir
        self.destination_dir = destination_dir
        
        # Patterns for clean_snip.
        self.hr_pattern = re.compile(r"^\s*([\-*_]\s*){3,}$")    # ---  ***  ___
        self.summary_tag = re.compile(r"<summary>(.*?)</summary>", re.IGNORECASE | re.DOTALL)
        self.snip_link = re.compile(r"🎧\s*\[[^\]]*\]\((https://share\.snipd\.com/[^)]+)\)")
        # H1 headers for potential multiple episodes in a single file.
        self.h1_pattern = re.compile(r"^#\s+.+$", re.MULTILINE)
    
    def process_podcasts(self) -> List[Path]:
        """Run the full podcasts processing pipeline."""
        podcasts = U.list_podcast_files(self.incoming_dir)
        if not podcasts:
            print("📻 No podcast files found to process")
            return []
        
        print(f"📻 Processing {len(podcasts)} podcast file(s)...")
        
        try:
            # 0. Split files with multiple episodes (if any).
            self._split_multi_episode_files()

            # Recompute the podcasts set after the split.
            podcasts = U.list_podcast_files(self.incoming_dir)

            # 1. Clean Snipd files.
            self._clean_snipd_files()
            
            # 2. Convert Markdown to HTML.
            self._convert_markdown_to_html()
            
            # 3. Rename and move files.
            renamed_files = U.rename_podcast_files(podcasts)
            moved_files = U.move_files(renamed_files, self.destination_dir)
            
            if moved_files:
                print(f"📻 {len(moved_files)} podcast file(s) moved to {self.destination_dir}")
            
            return moved_files
            
        except Exception as e:
            print(f"❌ Error processing podcasts: {e}")
            return []

    def _split_multi_episode_files(self):
        """Split files with multiple episodes (multiple H1) into separate files.

        Basic rule: each episode starts with a level-1 heading ('# Title').
        If 2+ H1 are detected in a file that matches the Snipd pattern, new .md
        files are created (one per episode) and the original file is deleted.
        """
        md_files = list(self.incoming_dir.rglob("*.md"))
        # Filter only podcast files.
        podcast_files = [f for f in md_files if U.is_podcast_file(f)]

        for md_file in podcast_files:
            try:
                text = md_file.read_text(encoding="utf-8", errors="ignore")
                # Find H1 positions.
                matches = list(self.h1_pattern.finditer(text))
                if len(matches) <= 1:
                    continue  # nothing to split

                print(f"✂️  Detected {len(matches)} episodes in: {md_file.name}. Splitting…")

                # Compute bounds for each block.
                starts = [m.start() for m in matches]
                ends = starts[1:] + [len(text)]

                new_files: list[Path] = []
                for i, (s, e) in enumerate(zip(starts, ends), start=1):
                    chunk = text[s:e].lstrip()  # clean leading blank headers
                    # Provisional name based on the original.
                    base_stem = md_file.stem
                    provisional = md_file.parent / f"{base_stem} - part {i}.md"
                    # Avoid collisions.
                    counter = 1
                    out_path = provisional
                    while out_path.exists():
                        out_path = md_file.parent / f"{base_stem} - part {i} ({counter}).md"
                        counter += 1
                    out_path.write_text(chunk, encoding="utf-8")
                    new_files.append(out_path)

                # Delete the original file after creating all new ones.
                try:
                    md_file.unlink()
                except Exception:
                    pass  # do not block if delete fails

                print(f"✂️  Split: {md_file.name} → {len(new_files)} files")

            except Exception as e:
                print(f"❌ Error splitting {md_file}: {e}")
    
    def _clean_snipd_files(self):
        """Clean Markdown files exported from Snipd."""
        md_files = list(self.incoming_dir.rglob("*.md"))
        
        # Filter only podcast files.
        podcast_files = [f for f in md_files if U.is_podcast_file(f)]
        
        if not podcast_files:
            print("🧹 No podcast files found to clean")
            return
        
        print(f"🧹 Cleaning {len(podcast_files)} podcast file(s)...")
        
        for md_file in podcast_files:
            try:
                original_text = md_file.read_text(encoding="utf-8", errors="ignore")
                text = original_text
                
                # Replace HTML line breaks <br/> and <br/>> for quoted text.
                text = re.sub(r"<br\s*/?>\s*>\s*", "\n> ", text)  # <br/>> -> new line with "> "
                text = re.sub(r"<br\s*/?>", "\n", text)           # <br/> -> simple new line
                
                # Replace audio links.
                text = self.snip_link.sub(self._replace_snip_link, text)
                
                text = self._lift_show_notes_section(text)
                lines_after = text.splitlines(keepends=True)
                cleaned_lines = self._clean_lines(lines_after)
                final_text = "".join(cleaned_lines)
                final_text = self._add_snip_index(final_text)

                if final_text != original_text:
                    md_file.write_text(final_text, encoding="utf-8")
                    print(f"🧹 Cleaned: {md_file}")
                    
            except Exception as e:
                print(f"❌ Error cleaning {md_file}: {e}")
    
    def _replace_snip_link(self, match: re.Match[str]) -> str:
        """Return embedded HTML for the snip link."""
        url = match.group(1)
        # Create a styled button that opens in a new tab.
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
        """Apply line-by-line cleanup rules."""
        cleaned: list[str] = []
        for line in lines:
            lower = line.lower()
            stripped = line.strip()

            if 'click to expand' in stripped.lower():
                continue
            
            # Remove <details> tags but keep their content.
            if '<details' in lower:
                continue
            if '</details>' in lower:
                continue
                
            # Convert <summary> to plain text (but remove if it is only "Click to expand").
            if '<summary' in lower:
                cleaned_text = self.summary_tag.sub(r"\1", line).strip()
                # Remove if summary content is only "Click to expand".
                if cleaned_text.lower() != "click to expand":
                    cleaned.append(cleaned_text + "\n")
                continue
            
            # Remove horizontal rules.
            if self.hr_pattern.match(line):
                continue
            
            cleaned.append(line)
        return cleaned

    def _add_snip_index(self, text: str) -> str:
        """Insert an index linking to each snip and add anchors to titles."""
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

        index_lines = [
            f"- [{title}](#{anchor})"
            for title, anchor in headings
            if anchor
        ]
        if not index_lines:
            return text

        index_block = f"{SNIP_INDEX_MARKER}\n" + "\n".join(index_lines) + "\n\n"
        return prefix + index_block + updated_block + suffix

    def _extract_anchor_id(self, attr_text: str | None) -> str | None:
        """Extract the #id identifier from a Markdown attribute block."""
        if not attr_text:
            return None
        match = re.search(r"#([A-Za-z0-9_-]+)", attr_text)
        return match.group(1) if match else None

    def _build_snip_anchor(self, title: str, index: int) -> str:
        """Generate predictable anchors for snip titles."""
        slug = self._slugify(title)
        prefix = f"snip-{index:02d}"
        return f"{prefix}-{slug}" if slug else prefix

    def _slugify(self, text: str) -> str:
        """Normalize titles to URL-safe slugs."""
        normalized = unicodedata.normalize("NFKD", text)
        ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        ascii_text = ascii_text.lower()
        ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text)
        return ascii_text.strip("-")

    def _lift_show_notes_section(self, text: str) -> str:
        """Convert <details> blocks into H2 sections and move trailing metadata."""
        details_re = re.compile(
            r"<details>\s*<summary>(?P<title>.*?)</summary>(?P<body>.*?)</details>"
            r"(?P<trailing>(?:\s*\n- [^\n]+)*)",
            re.IGNORECASE | re.DOTALL,
        )

        def _repl(match: re.Match[str]) -> str:
            raw_title = match.group("title") or ""
            title = self.summary_tag.sub(r"\1", raw_title).strip()
            if not title:
                title = "Show notes"

            body = (match.group("body") or "").strip()
            trailing = (match.group("trailing") or "").strip()

            parts: list[str] = []
            if trailing:
                parts.append(trailing)

            heading = f"## {title}\n\n{body}\n\n" if body else f"## {title}\n\n"
            parts.append(heading)

            return "\n\n".join(parts)

        return details_re.sub(_repl, text)
    
    def _convert_markdown_to_html(self):
        """Convert podcast Markdown files to HTML."""
        md_files = [p for p in self.incoming_dir.rglob("*.md") 
                   if U.is_podcast_file(p) and not p.with_suffix(".html").exists()]
        
        if not md_files:
            print("🔄 No podcast Markdown files pending conversion")
            return
        
        print(f"🔄 Converting {len(md_files)} podcast file(s) to HTML...")
        
        for md_file in md_files:
            try:
                html_path = md_file.with_suffix(".html")
                
                # Do not overwrite if it already exists.
                if html_path.exists():
                    continue
                
                md_text = md_file.read_text(encoding="utf-8")
                html_body = self._md_to_html(md_text)
                full_html = self._wrap_html(md_file.stem, html_body)
                html_path.write_text(full_html, encoding="utf-8")
                
                # Show relative path if possible.
                try:
                    display_path = html_path.relative_to(Path.cwd()) if html_path.is_absolute() else html_path
                except ValueError:
                    display_path = html_path
                print(f"✅ HTML generated: {display_path}")
                
            except Exception as e:
                print(f"❌ Error converting {md_file}: {e}")
    
    def _md_to_html(self, md_text: str) -> str:
        """Convert Markdown text to HTML and return only the body."""
        return U.markdown_to_html_body(md_text)
    
    def _wrap_html(self, title: str, body: str) -> str:
        """Wrap content in HTML with styles and the podcast color."""
        return U.wrap_html(title, body, "#667eea")
