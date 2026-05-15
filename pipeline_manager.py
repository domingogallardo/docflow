#!/usr/bin/env python3
"""
DocumentProcessor - main class for document processing.
"""
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence, Tuple
from datetime import datetime

import utils as U
import config as cfg
from pdf_processor import PDFProcessor
from instapaper_processor import InstapaperProcessor
from podcast_processor import PodcastProcessor
from image_processor import ImageProcessor
from markdown_processor import MarkdownProcessor
from path_utils import unique_path
from web_clipper_wrapper import (
    URL_RE,
    download_url_to_markdown,
    read_urls_from_file,
)

PIPELINE_STEPS = (
    ("urls", "process_web_urls"),
    ("tweets", "process_tweets_pipeline"),
    ("podcasts", "process_podcasts"),
    ("posts", "process_instapaper_posts"),
    ("pdfs", "process_pdfs"),
    ("images", "process_images"),
    ("md", "process_markdown"),
)
TARGET_HANDLERS = {name: method for name, method in PIPELINE_STEPS}
PIPELINE_TARGETS = tuple(name for name, _ in PIPELINE_STEPS)
from utils.tweet_to_markdown import fetch_tweet_thread_markdown
from utils.x_likes_fetcher import (
    LikeTweet,
    fetch_like_items_with_state,
    fetch_post_items_with_state,
    fetch_reply_items_with_state,
)


class DocumentProcessor:
    """Main document processor with modular, configurable logic."""
    
    def __init__(self, base_dir: Path, year: int):
        self.base_dir = Path(base_dir)
        self.year = year
        self.incoming = self.base_dir / "Incoming"
        self.posts_dest = self._year_dir("Posts")
        self.pdfs_dest = self._year_dir("Pdfs")
        self.podcasts_dest = self._year_dir("Podcasts")
        self.images_dest = self._year_dir("Images")
        self.tweets_dest = self._year_dir("Tweets")
        self.processed_history = self.incoming / "processed_history.txt"
        self.tweets_processed = self.incoming / "tweets_processed.txt"
        self.tweets_failed = self.incoming / "tweets_failed.txt"
        self.tweets_posted_processed = self.incoming / "tweets_posted_processed.txt"
        self.tweets_posted_failed = self.incoming / "tweets_posted_failed.txt"
        self.tweets_replies_processed = self.incoming / "tweets_replies_processed.txt"
        self.tweets_replies_failed = self.incoming / "tweets_replies_failed.txt"
        self.links_file = self.incoming / "links.txt"
        self.links_failed = self.incoming / "links_failed.txt"

        self.pdf_processor = PDFProcessor(self.incoming, self.pdfs_dest)
        self.instapaper_processor = InstapaperProcessor(self.incoming, self.posts_dest)
        self.podcast_processor = PodcastProcessor(self.incoming, self.podcasts_dest)
        self.image_processor = ImageProcessor(self.incoming, self.images_dest)
        self.markdown_processor = MarkdownProcessor(self.incoming, self.posts_dest)
        self.tweet_processor = MarkdownProcessor(self.incoming, self.tweets_dest)
        self._history: List[Path] = []

    def _year_dir(self, kind: str) -> Path:
        """Build the yearly path for the given kind."""
        return self.base_dir / kind / f"{kind} {self.year}"

    def _run_and_remember(self, fn: Callable[[], List[Path]]) -> List[Path]:
        """Run a processing function and record its results."""
        paths = fn()
        self._remember(paths)
        return paths

    def process_tweet_urls(self) -> List[Path]:
        """Fetch recent likes/posts from X and generate Markdown in Incoming/."""
        generated = self._process_tweet_source(
            capture_source="liked",
            timeline_label="your likes",
            processed_path=self.tweets_processed,
            failed_path=self.tweets_failed,
            max_setting_name="TWEET_LIKES_MAX",
            fetch_items=self._fetch_like_items,
        )
        if cfg.TWEET_POSTS_URL:
            generated = self._merge_paths(
                generated,
                self._process_tweet_source(
                    capture_source="posted",
                    timeline_label="your posted tweets/reposts",
                    processed_path=self.tweets_posted_processed,
                    failed_path=self.tweets_posted_failed,
                    max_setting_name="TWEET_POSTS_MAX",
                    fetch_items=self._fetch_post_items,
                    default_posted_kind="post",
                ),
            )
            generated = self._merge_paths(
                generated,
                self._process_tweet_source(
                    capture_source="posted",
                    timeline_label="your replies",
                    processed_path=self.tweets_replies_processed,
                    failed_path=self.tweets_replies_failed,
                    max_setting_name="TWEET_REPLIES_MAX",
                    fetch_items=self._fetch_reply_items,
                    default_posted_kind="reply",
                    skip_processed_paths=(self.tweets_posted_processed,),
                ),
            )
        return generated

    def _process_tweet_source(
        self,
        *,
        capture_source: str,
        timeline_label: str,
        processed_path: Path,
        failed_path: Path,
        max_setting_name: str,
        fetch_items: Callable[..., Tuple[List[LikeTweet], bool, int]],
        default_posted_kind: str | None = None,
        skip_processed_paths: Sequence[Path] = (),
    ) -> List[Path]:
        failed_urls = self._load_failed_urls(failed_path=failed_path)
        processed_urls = self._load_processed_urls(processed_path=processed_path)
        skip_processed_set = {
            url
            for skip_path in skip_processed_paths
            for url in self._load_processed_urls(processed_path=skip_path)
        }
        processed_set = set(processed_urls) | skip_processed_set
        pending_failed = {url: None for url in failed_urls if url not in processed_set}
        fetch_error = False
        stop_found = False
        total_articles = 0
        last_processed = self._last_processed_tweet_url(processed_path=processed_path)

        try:
            items, stop_found, total_articles = fetch_items(last_processed=last_processed)
        except Exception as exc:
            print(f"🐦 Could not read X {timeline_label}: {exc}")
            items = []
            fetch_error = True

        if items and last_processed and not stop_found:
            anchor_url = self._first_processed_like_url(items, processed_set)
            if anchor_url:
                processed_urls = self._promote_processed_url(
                    processed_urls,
                    anchor_url,
                    processed_path=processed_path,
                )
                processed_set = set(processed_urls) | skip_processed_set
            else:
                print(
                    "⚠️  Last processed URL not found in "
                    f"{timeline_label}; check the {max_setting_name} limit "
                    f"(visible articles: {total_articles})."
                )

        if not items and not pending_failed:
            self._write_failed_urls(list(pending_failed.keys()), failed_path=failed_path)
            if not fetch_error:
                print(f"🐦 No new tweets found in {timeline_label}")
            return []

        fresh_items = [item for item in items if item.url not in processed_set]
        fresh_url_set = {item.url for item in fresh_items}
        retry_urls = [url for url in pending_failed if url not in fresh_url_set]

        if not fresh_items and not retry_urls:
            self._write_failed_urls(list(pending_failed.keys()), failed_path=failed_path)
            print(f"🐦 No new {capture_source} tweets pending (everything is already processed).")
            return []

        if retry_urls:
            print(f"🐦 Retrying {len(retry_urls)} failed {capture_source} tweet(s).")

        generated: List[Path] = []
        written_fresh_urls: List[str] = []
        written_retry_urls: List[str] = []
        queue: List[LikeTweet] = list(fresh_items) + [
            LikeTweet(url=url, posted_kind=default_posted_kind) for url in retry_urls
        ]

        for item in queue:
            posted_kind = item.posted_kind or default_posted_kind
            try:
                markdown, filename = fetch_tweet_thread_markdown(
                    item.url,
                    # Use storage_state to avoid X's login wall.
                    storage_state=cfg.TWEET_LIKES_STATE,
                    context_author_handle=item.author_handle,
                    context_time_text=item.time_text,
                    context_time_datetime=item.time_datetime,
                    capture_source=capture_source,
                    posted_kind=posted_kind,
                    reply_parent_url=item.reply_to_url,
                )
            except Exception as exc:
                print(f"❌ Error processing {item.url}: {exc}")
                pending_failed.setdefault(item.url, None)
                continue

            destination = self._unique_destination(self.incoming / filename)
            destination.write_text(markdown, encoding="utf-8")
            generated.append(destination)
            if item.url in fresh_url_set:
                written_fresh_urls.append(item.url)
            else:
                written_retry_urls.append(item.url)
            pending_failed.pop(item.url, None)
            print(f"🐦 Tweet saved as {destination.name}")

        if written_fresh_urls or written_retry_urls:
            self._record_processed_urls(
                fresh_urls=written_fresh_urls,
                retry_urls=written_retry_urls,
                processed_path=processed_path,
            )
        self._write_failed_urls(list(pending_failed.keys()), failed_path=failed_path)

        return generated

    def _unique_destination(self, target: Path) -> Path:
        """Generate a unique name to avoid overwriting existing files."""
        return unique_path(target)

    def _fetch_like_items(
        self,
        *,
        last_processed: str | None,
    ) -> Tuple[List[LikeTweet], bool, int]:
        if not cfg.TWEET_LIKES_STATE:
            raise RuntimeError("Configure TWEET_LIKES_STATE with the storage_state exported from X.")
        items, stop_found, total_articles = fetch_like_items_with_state(
            cfg.TWEET_LIKES_STATE,
            likes_url=cfg.TWEET_LIKES_URL,
            max_tweets=cfg.TWEET_LIKES_MAX,
            stop_at_url=last_processed,
            headless=True,
        )
        return items, stop_found, total_articles

    def _fetch_post_items(
        self,
        *,
        last_processed: str | None,
    ) -> Tuple[List[LikeTweet], bool, int]:
        if not cfg.TWEET_LIKES_STATE:
            raise RuntimeError("Configure TWEET_LIKES_STATE with the storage_state exported from X.")
        if not cfg.TWEET_POSTS_URL:
            return [], False, 0
        items, stop_found, total_articles = fetch_post_items_with_state(
            cfg.TWEET_LIKES_STATE,
            posts_url=cfg.TWEET_POSTS_URL,
            max_tweets=cfg.TWEET_POSTS_MAX,
            stop_at_url=last_processed,
            headless=True,
        )
        return items, stop_found, total_articles

    def _fetch_reply_items(
        self,
        *,
        last_processed: str | None,
    ) -> Tuple[List[LikeTweet], bool, int]:
        if not cfg.TWEET_LIKES_STATE:
            raise RuntimeError("Configure TWEET_LIKES_STATE with the storage_state exported from X.")
        if not cfg.TWEET_POSTS_URL:
            return [], False, 0
        replies_url = cfg.TWEET_REPLIES_URL or cfg.TWEET_POSTS_URL.rstrip("/") + "/with_replies"
        items, stop_found, total_articles = fetch_reply_items_with_state(
            cfg.TWEET_LIKES_STATE,
            replies_url=replies_url,
            max_tweets=cfg.TWEET_REPLIES_MAX,
            stop_at_url=last_processed,
            headless=True,
        )
        return items, stop_found, total_articles

    def _last_processed_tweet_url(self, *, processed_path: Path | None = None) -> Optional[str]:
        lines = self._load_processed_urls(processed_path=processed_path)
        if not lines:
            return None
        return lines[0]

    @staticmethod
    def _load_url_file(path: Path) -> List[str]:
        if not path.exists():
            return []
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
        return [line for line in lines if line]

    def _load_processed_urls(self, *, processed_path: Path | None = None) -> List[str]:
        return self._load_url_file(processed_path or self.tweets_processed)

    def _load_failed_urls(self, *, failed_path: Path | None = None) -> List[str]:
        return self._load_url_file(failed_path or self.tweets_failed)

    @staticmethod
    def _write_url_file(path: Path, urls: List[str]) -> None:
        if not urls:
            if path.exists():
                path.unlink()
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(urls) + "\n", encoding="utf-8")

    def _write_failed_urls(self, urls: List[str], *, failed_path: Path | None = None) -> None:
        self._write_url_file(failed_path or self.tweets_failed, urls)

    def _write_processed_urls(self, urls: List[str], *, processed_path: Path | None = None) -> None:
        self._write_url_file(processed_path or self.tweets_processed, urls)

    @staticmethod
    def _append_url_history(urls: Sequence[str], *, history_path: Path) -> None:
        if not urls:
            return
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines_new = [f"{url} - {timestamp}\n" for url in urls]
        old_content = history_path.read_text(encoding="utf-8") if history_path.exists() else ""
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text("".join(lines_new) + old_content, encoding="utf-8")

    @staticmethod
    def _append_link_failures(failures: Sequence[Tuple[str, str]], *, failed_path: Path) -> None:
        if not failures:
            return
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        failed_path.parent.mkdir(parents=True, exist_ok=True)
        with failed_path.open("a", encoding="utf-8") as fh:
            for url, reason in failures:
                clean_reason = " ".join(str(reason).replace("\t", " ").split())
                fh.write(f"{timestamp}\t{url}\t{clean_reason}\n")

    @staticmethod
    def _remove_urls_from_links_file(path: Path, processed_urls: Sequence[str]) -> None:
        if not processed_urls or not path.exists():
            return

        processed_set = set(processed_urls)
        kept_lines: List[str] = []
        changed = False
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            found_urls = {match.group(0).rstrip(").,;") for match in URL_RE.finditer(line)}
            if found_urls & processed_set:
                changed = True
                continue
            kept_lines.append(line)

        if changed:
            new_content = "\n".join(kept_lines)
            if new_content:
                new_content += "\n"
            path.write_text(new_content, encoding="utf-8")

    @staticmethod
    def _dedupe_urls(urls: Sequence[str]) -> List[str]:
        seen: set[str] = set()
        ordered: List[str] = []
        for url in urls:
            if not url or url in seen:
                continue
            seen.add(url)
            ordered.append(url)
        return ordered

    def _record_processed_urls(
        self,
        *,
        fresh_urls: List[str],
        retry_urls: List[str],
        processed_path: Path | None = None,
    ) -> None:
        fresh = self._dedupe_urls(fresh_urls)
        retries = self._dedupe_urls(retry_urls)
        if not fresh and not retries:
            return

        existing = self._load_processed_urls(processed_path=processed_path)
        fresh_set = set(fresh)
        retry_set = set(retries)
        middle = [url for url in existing if url not in fresh_set and url not in retry_set]
        ordered = [*fresh, *middle, *retries]
        self._write_processed_urls(ordered, processed_path=processed_path)

    def _promote_processed_url(
        self,
        processed_urls: Sequence[str],
        anchor_url: str,
        *,
        processed_path: Path | None = None,
    ) -> List[str]:
        if not processed_urls:
            return []
        if processed_urls[0] == anchor_url:
            return list(processed_urls)
        if anchor_url not in processed_urls:
            return list(processed_urls)

        reordered = [anchor_url, *[url for url in processed_urls if url != anchor_url]]
        self._write_processed_urls(reordered, processed_path=processed_path)
        return reordered

    @staticmethod
    def _first_processed_like_url(likes: Sequence[LikeTweet], processed_set: set[str]) -> str | None:
        for like in likes:
            if like.url in processed_set:
                return like.url
        return None

    def process_podcasts(self) -> List[Path]:
        """Process podcast files with the unified processor."""
        # Use the unified processor for the whole podcasts pipeline.
        return self._run_and_remember(self.podcast_processor.process_podcasts)
    
    def process_instapaper_posts(self) -> List[Path]:
        """Process Instapaper web posts with the unified pipeline."""
        # Use the unified processor for the whole Instapaper pipeline.
        moved_posts = self.instapaper_processor.process_instapaper_posts()

        self._remember(moved_posts)
        return moved_posts
    
    def process_pdfs(self) -> List[Path]:
        """Process PDFs using the specialized processor."""
        return self._run_and_remember(self.pdf_processor.process_pdfs)
    
    def process_images(self) -> List[Path]:
        """Process images by moving them and generating the yearly gallery."""
        return self._run_and_remember(self.image_processor.process_images)

    def process_markdown(self) -> List[Path]:
        """Process generic Markdown files."""
        return self._run_and_remember(self.markdown_processor.process_markdown)

    def process_web_urls(self) -> List[Path]:
        """Download article URLs from Incoming/links.txt as Markdown files."""
        urls = read_urls_from_file(self.links_file)
        if not urls:
            print("🔗 No URLs found to download")
            return []

        generated: List[Path] = []
        processed_urls: List[str] = []
        failures: List[Tuple[str, str]] = []

        print(f"🔗 Downloading {len(urls)} URL(s) as Markdown...")
        for url in urls:
            try:
                result = download_url_to_markdown(url, output_dir=self.incoming)
            except Exception as exc:
                failures.append((url, str(exc)))
                print(f"❌ Error downloading {url}: {exc}")
                continue

            generated.append(result.output_path)
            processed_urls.append(url)
            print(f"✅ URL saved as Markdown: {result.output_path.name}")

        if processed_urls:
            self._remove_urls_from_links_file(self.links_file, processed_urls)
            self._append_url_history(processed_urls, history_path=self.processed_history)
            print(f"🔗 {len(processed_urls)} URL(s) processed and removed from links.txt")

        if failures:
            self._append_link_failures(failures, failed_path=self.links_failed)
            print(f"⚠️  {len(failures)} URL(s) failed; see {self.links_failed}")

        return generated
    
    def process_tweets_pipeline(self, *, log_empty_conversion: bool = True) -> List[Path]:
        """Process the tweet queue and move results to the yearly Tweets folder."""
        generated = self.process_tweet_urls()
        tweet_markdown = self._merge_paths(self._list_tweet_markdown(), generated)
        return self._process_tweet_markdown_subset(tweet_markdown, log_empty=log_empty_conversion)

    def process_targets(self, targets: Iterable[str], *, log_empty_tweets: bool = True) -> bool:
        """Run a subset of the pipeline for the given targets."""
        try:
            for target in targets:
                handler_name = TARGET_HANDLERS[target]
                handler = getattr(self, handler_name)
                if target == "tweets":
                    handler(log_empty_conversion=log_empty_tweets)
                else:
                    handler()
            self.register_all_files()
            print("Pipeline completed ✅")
            return True
        except Exception as e:
            print(f"❌ Pipeline error: {e}")
            return False

    def _process_tweet_markdown_subset(
        self,
        markdown_files: Iterable[Path],
        *,
        log_empty: bool = True,
    ) -> List[Path]:
        files = [Path(path) for path in markdown_files if Path(path).exists()]
        if not files:
            if log_empty:
                print("🐦 No new tweets to convert to HTML")
            return []
        return self._run_and_remember(lambda: self.tweet_processor.process_tweet_markdown_subset(files))
    
    def register_all_files(self) -> None:
        """Register all processed files in history."""
        if self._history:
            U.register_paths(
                self._history,
                base_dir=self.base_dir,
                historial_path=self.processed_history,
            )
            self._history = []
    
    def process_all(self) -> bool:
        """Run the full pipeline."""
        return self.process_targets(PIPELINE_TARGETS, log_empty_tweets=False)

    def _remember(self, paths: List[Path]) -> None:
        self._history.extend(paths)

    @staticmethod
    def _merge_paths(primary: Iterable[Path], secondary: Iterable[Path]) -> List[Path]:
        seen: set[Path] = set()
        merged: List[Path] = []
        for path in list(primary) + list(secondary):
            path = Path(path)
            if path in seen:
                continue
            seen.add(path)
            merged.append(path)
        return merged

    def _list_tweet_markdown(self) -> List[Path]:
        return [
            path for path in self.incoming.rglob("*.md")
            if self.tweet_processor.is_tweet_markdown(path)
        ]
