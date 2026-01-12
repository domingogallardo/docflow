#!/usr/bin/env python3
"""
InstapaperProcessor - unified module for full processing of Instapaper articles.

Note: the processor works only with the HTML delivered by Instapaper. External
resources (images, videos, etc.) are linked without downloading them, so their
availability depends on the origin server. If the origin service (for example,
Medium) blocked the download when Instapaper created its copy, those images are
already missing and the pipeline cannot recover them.
"""
from __future__ import annotations
import re
import time
import requests
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
from bs4 import BeautifulSoup
from markdownify import markdownify as md

from config import INSTAPAPER_USERNAME, INSTAPAPER_PASSWORD, OPENAI_KEY
import utils as U
from title_ai import TitleAIUpdater, rename_markdown_pair
from openai_client import build_openai_client
from path_utils import unique_path


class InstapaperDownloadRegistry:
    """Persistent registry to avoid repeated Instapaper downloads."""

    def __init__(self, path: Path):
        self.path = path
        self.entries: Dict[str, Dict[str, object]] = {}
        self._batch_depth = 0
        self._dirty = False
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return

        try:
            content = self.path.read_text(encoding="utf-8")
        except Exception:
            return

        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split("\t")
            if len(parts) < 2:
                continue

            article_id = parts[0].strip()
            timestamp = parts[-1].strip() if len(parts) > 1 else ""

            if not article_id:
                continue

            self.entries[article_id] = {
                "timestamp": timestamp,
            }

    def should_skip(self, article_id: str) -> bool:
        return article_id in self.entries

    def mark_downloaded(self, article_id: str) -> None:
        timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        self.entries[article_id] = {
            "timestamp": timestamp,
        }
        if self._batch_depth:
            self._dirty = True
        else:
            self._persist()

    @contextmanager
    def batch(self):
        """Accumulate writes and persist on exit."""
        self._batch_depth += 1
        try:
            yield self
        finally:
            self._batch_depth -= 1
            if self._batch_depth == 0 and self._dirty:
                self._persist()
                self._dirty = False

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for article_id, data in self.entries.items():
            timestamp = str(data.get("timestamp") or "")
            lines.append(f"{article_id}\t{timestamp}")

        payload = "\n".join(lines) + ("\n" if lines else "")
        self.path.write_text(payload, encoding="utf-8")


class InstapaperProcessor:
    """Unified processor for the full Instapaper articles pipeline."""
    
    def __init__(self, incoming_dir: Path, destination_dir: Path):
        self.incoming_dir = incoming_dir
        self.destination_dir = destination_dir
        self.session = None
        self.openai_client = build_openai_client(OPENAI_KEY)
        self.title_updater = TitleAIUpdater(self.openai_client)
        self.download_registry = InstapaperDownloadRegistry(
            self.incoming_dir / ".instapaper_downloads.txt"
        )


    def process_instapaper_posts(self) -> List[Path]:
        """Run the full processing pipeline for Instapaper posts."""
        print("📄 Processing Instapaper posts...")
        
        try:
            # 1. Download Instapaper articles
            if not self._download_from_instapaper():
                print("⚠️ No Instapaper articles downloaded; continuing with existing files...")
            
            # 2. Convert HTML to Markdown
            self._convert_html_to_markdown()
            
            # 3. Fix HTML encoding
            self._fix_html_encoding()

            # 4. Reduce images
            self._reduce_images_width()

            # 5. Add margins
            self._add_margins()

            # 6. Generate titles with AI
            self._update_titles_with_ai()

            # 7. Move processed files
            posts = self._list_processed_files()
            if posts:
                moved_posts = self._move_files_to_destination(posts)
                print(f"📄 {len(moved_posts)} post(s) moved to {self.destination_dir}")
                return moved_posts
            else:
                print("📄 No processed posts found to move")
                return []
                
        except Exception as e:
            print(f"❌ Error processing Instapaper: {e}")
            return []
    
    def _download_from_instapaper(self) -> bool:
        """Download articles from Instapaper."""
        if not self._has_instapaper_credentials():
            print("❌ Instapaper credentials not configured")
            return False

        try:
            self._init_instapaper_session()
            login_response = self._login_instapaper()

            if not self._is_login_successful(login_response):
                print("❌ Instapaper credentials are incorrect")
                return False

            print("✅ Instapaper login successful")

            first_articles, has_more = self._get_article_ids(1)
            if not first_articles:
                print("📚 No new Instapaper articles to download")
                return True  # Not an error, there's simply nothing to do

            print("📚 Starting Instapaper article download...")
            with open("failed.txt", "a+") as failure_log, self.download_registry.batch():
                self._download_articles_pages(first_articles, has_more, failure_log)

            print("📚 Instapaper download completed")
            return True

        except Exception as e:
            print(f"❌ Error downloading from Instapaper: {e}")
            return False

    def _has_instapaper_credentials(self) -> bool:
        return bool(INSTAPAPER_USERNAME and INSTAPAPER_PASSWORD)

    def _init_instapaper_session(self) -> None:
        self.session = requests.Session()

    def _login_instapaper(self):
        return self.session.post(
            "https://www.instapaper.com/user/login",
            data={
                "username": INSTAPAPER_USERNAME,
                "password": INSTAPAPER_PASSWORD,
                "keep_logged_in": "yes",
            },
        )

    def _is_login_successful(self, login_response) -> bool:
        login_successful = True

        if login_response.status_code >= 400:
            print(f"❌ HTTP error {login_response.status_code} - wrong URL or server unavailable")
            login_successful = False
        elif "login" in login_response.url:
            print("❌ Redirected to login page - incorrect credentials")
            login_successful = False

        soup = BeautifulSoup(login_response.text, "html.parser")
        error_messages = soup.find_all(class_="error")
        if error_messages:
            print("❌ Error messages found on the login page")
            for error in error_messages:
                print(f"   - {error.get_text().strip()}")
            login_successful = False

        login_form = soup.find("form")
        if login_form and "login" in login_form.get("action", ""):
            print("❌ Login form found - not logged in")
            login_successful = False

        return login_successful

    def _download_articles_pages(self, first_articles, has_more, failure_log) -> None:
        page = 1
        while has_more or page == 1:
            print(f"Page {page}")
            if page == 1:
                articles = first_articles
            else:
                articles, has_more = self._get_article_ids(page)

            self._download_article_batch(articles, failure_log)
            page += 1

    def _download_article_batch(self, articles, failure_log) -> None:
        for article_id in articles:
            if self.download_registry.should_skip(article_id):
                print(f"  {article_id}: ⏭️  already downloaded (no changes)")
                continue

            print(f"  {article_id}: ", end="")
            start = time.time()
            try:
                self._download_article(article_id)
                self.download_registry.mark_downloaded(article_id)
                duration = time.time() - start
                print(f"{round(duration, 2)} seconds")
            except Exception as e:
                print("failed!")
                failure_log.write(f"{article_id}\t{str(e)}\n")
                failure_log.flush()

    def _get_article_ids(self, page: int = 1) -> Tuple[List[str], bool]:
        """Get article IDs for a page."""
        url = f"https://www.instapaper.com/u/{page}"
        r = self.session.get(url)

        soup = BeautifulSoup(r.text, "html.parser")
        container = soup.find(id="article_list")
        if not container:
            return [], False

        articles = container.find_all("article")

        items: List[str] = []
        for art in articles:
            aid = (art.get("id") or "").replace("article_", "")
            if not aid:
                continue
            items.append(aid)

        has_more = soup.find(class_="paginate_older") is not None
        return items, has_more

    
    def _download_article(self, article_id: str) -> Path:
        """Download a specific article.

        Only the HTML returned by Instapaper is persisted. ``<img>`` tags are
        kept with their original URLs and remote resources are **not**
        downloaded. This means that if the origin server blocks hotlinking,
        images might not display in the stored copy.
        """
        r = self.session.get(f"https://www.instapaper.com/read/{article_id}")
        soup = BeautifulSoup(r.text, "html.parser")

        title_el = soup.find(id="titlebar").find("h1")
        raw_title = title_el.getText() if title_el else (soup.title.string if soup.title else f"Instapaper {article_id}")
        title = raw_title

        origin = soup.find(id="titlebar").find(class_="origin_line")
        content_node = soup.find(id="story")
        content = content_node.decode_contents() if content_node else ""

        # --- ROBUST FILENAME ---
        safe = "".join([c for c in title if c.isalpha() or c.isdigit() or c == " "]).strip()
        if not safe:
            safe = f"Instapaper {article_id}"
        file_name = self._truncate_filename(safe, ".html")
        file_path = self.incoming_dir / file_name

        origin_html = str(origin) if origin else ""
        html_content = self._build_article_html(
            title=title,
            origin_html=origin_html,
            article_id=article_id,
            content=content,
        )

        file_path.write_text(html_content, encoding="utf-8")
        return file_path

    def _build_article_html(self, *, title: str, origin_html: str, article_id: str, content: str) -> str:
        source_meta = '<meta name="docflow-source" content="instapaper">\n'
        return (
            "<!DOCTYPE html>\n"
            "<html>\n"
            "<head>\n"
            '<meta charset="UTF-8">\n'
            f"{source_meta}"
            f"<title>{title}</title>\n"
            "</head>\n<body>\n"
            f"<h1>{title}</h1>\n"
            f"<div id='origin'>{origin_html} · {article_id}</div>\n"
            f"{content}\n"
            "</body>\n</html>"
        )

    def _truncate_filename(self, name, extension, max_length=200):
        """Truncate long filenames."""
        total_length = len(name) + len(extension) + 1
        if total_length > max_length:
            name = name[:max_length - len(extension) - 1]
        return name + extension
    
    def _convert_html_to_markdown(self):
        """Convert HTML files to Markdown."""
        html_files = [
            path for path in U.iter_html_files(self.incoming_dir)
            if not path.with_suffix('.md').exists() and self._is_instapaper_html(path)
        ]
        
        if not html_files:
            print("📄 No pending HTML files to convert to Markdown")
            return
        
        print(f"Converting {len(html_files)} HTML files to Markdown")
        
        for html_file in html_files:
            try:
                html_content = html_file.read_text(encoding='utf-8')

                markdown_body = md(html_content, heading_style="ATX")
                
                front_matter = (
                    "---\n"
                    "source: instapaper\n"
                    "---\n\n"
                )
                markdown_content = front_matter + markdown_body

                md_file = html_file.with_suffix('.md')
                md_file.write_text(markdown_content, encoding='utf-8')
                print(f"✅ Markdown saved: {md_file}")
            except Exception as e:
                print(f"❌ Error converting {html_file}: {e}")
                    
    def _fix_html_encoding(self):
        """Fix HTML file encoding."""
        html_files = list(U.iter_html_files(self.incoming_dir))

        if not html_files:
            print("🔧 No HTML files to process encoding")
            return
        
        for html_file in html_files:
            try:
                content = html_file.read_text(encoding='utf-8')
                
                if not self._has_charset_meta(content):
                    new_content = self._insert_charset_meta(content, 'utf-8')
                    html_file.write_text(new_content, encoding='utf-8')
                    print(f"🔧 Encoding updated: {html_file}")
            except Exception as e:
                print(f"❌ Error processing encoding for {html_file}: {e}")

    def _has_charset_meta(self, content):
        """Check whether the HTML already has a charset meta."""
        charset_regex = re.compile(
            r'<meta\s+[^>]*charset\s*=|<meta\s+[^>]*http-equiv=["\']Content-Type["\'][^>]*charset=',
            re.IGNORECASE
        )
        return charset_regex.search(content) is not None
    
    def _insert_charset_meta(self, content, encoding):
        """Insert a charset meta into HTML."""
        head_tag = re.search(r"<head[^>]*>", content, re.IGNORECASE)
        meta_tag = f'<meta charset="{encoding}">\n'

        if head_tag:
            insert_pos = head_tag.end()
            return content[:insert_pos] + "\n" + meta_tag + content[insert_pos:]
        else:
            return meta_tag + content

    def _reduce_images_width(self):
        """Reduce image widths in HTML files without remote measurement.

        Policy: if the HTML declares a width greater than 300px, we cap it at
        300px and remove height to preserve aspect ratio. If no width is
        declared, we leave the element untouched and rely on the global CSS
        `img { max-width: 300px; height: auto; }` injected in _add_margins().
        """
        html_files = list(U.iter_html_files(self.incoming_dir))

        if not html_files:
            print("🖼️  No HTML files to process images")
            return

        max_width = 300
        for html_file in html_files:
            try:
                # Minimal log to identify which file is being processed.
                print(f"🖼️  Checking images: {html_file}")
                with open(html_file, 'r', encoding='utf-8') as f:
                    soup = BeautifulSoup(f, 'html.parser')
                
                modified = False
                for img in soup.find_all('img'):
                    src = img.get('src')
                    if not src:
                        continue
                    
                    # Use the declared width from the HTML; do not do remote measurement.
                    width_attr = img.get('width')
                    width = None
                    if width_attr:
                        try:
                            width = int(str(width_attr).strip())
                        except Exception:
                            width = None
                    
                    if width is not None and width > max_width:
                        img['width'] = str(max_width)
                        if 'height' in img.attrs:
                            del img['height']
                        modified = True
                        print(f"🖼️  Adjusting: {src} ({width}px → {max_width}px)")
                
                if modified:
                    with open(html_file, 'w', encoding='utf-8') as f:
                        f.write(str(soup))
                    print(f"✅ Images updated: {html_file}")
                    
            except Exception as e:
                print(f"❌ Error processing images in {html_file}: {e}")
    
    def _add_margins(self):
        """Add margins to HTML files."""
        U.add_margins_to_html_files(self.incoming_dir)
    
    # Note: _get_image_width removed (unused; width is handled via HTML or CSS).

    def _update_titles_with_ai(self):
        """Generate attractive titles with AI for Markdown files."""
        md_files = [
            p for p in self.incoming_dir.rglob("*.md")
            if self._is_instapaper_markdown(p)
        ]
        self.title_updater.update_titles(md_files, rename_markdown_pair)

    def _is_instapaper_markdown(self, path: Path) -> bool:
        """Determine whether a Markdown file comes from an Instapaper conversion."""
        html_path = path.with_suffix(".html")
        return html_path.exists() and self._is_instapaper_html(html_path)

    def _is_instapaper_html(self, path: Path) -> bool:
        """Determine whether an HTML belongs to an Instapaper export."""
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return False
        try:
            soup = BeautifulSoup(content, "html.parser")
        except Exception:
            return False
        meta = soup.find("meta", attrs={"name": "docflow-source"})
        if not meta:
            return False
        return str(meta.get("content", "")).strip().lower() == "instapaper"
    

    # Note: title generation uses title_ai.TitleAIUpdater.

    def _list_processed_files(self) -> List[Path]:
        """List processed files (HTML and Markdown)."""
        exts = {'.html', '.htm', '.md'}
        processed: List[Path] = []

        for file_path in self.incoming_dir.rglob("*"):
            if not file_path.is_file() or file_path.suffix.lower() not in exts:
                continue

            suffix = file_path.suffix.lower()
            if suffix == '.md' and not self._is_instapaper_markdown(file_path):
                continue
            if suffix in {'.html', '.htm'} and not self._is_instapaper_html(file_path):
                continue

            processed.append(file_path)

        return processed
    
    def _move_files_to_destination(self, files: List[Path]) -> List[Path]:
        """Move files to the final destination."""
        self.destination_dir.mkdir(parents=True, exist_ok=True)
        moved_files = []
        
        for file_path in files:
            dest_path = unique_path(self.destination_dir / file_path.name)
            file_path.rename(dest_path)
            moved_files.append(dest_path)
        
        return moved_files 
