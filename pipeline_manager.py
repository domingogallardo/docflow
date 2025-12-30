#!/usr/bin/env python3
"""
DocumentProcessor - main class for document processing.
"""
from pathlib import Path
from typing import Callable, Iterable, List, Optional

import utils as U
import config as cfg
from pdf_processor import PDFProcessor
from instapaper_processor import InstapaperProcessor
from podcast_processor import PodcastProcessor
from image_processor import ImageProcessor
from markdown_processor import MarkdownProcessor
from path_utils import unique_path

PIPELINE_STEPS = (
    ("tweets", "process_tweets_pipeline"),
    ("podcasts", "process_podcasts"),
    ("posts", "process_instapaper_posts"),
    ("pdfs", "process_pdfs"),
    ("images", "process_images"),
    ("md", "process_markdown"),
)
TARGET_HANDLERS = {name: method for name, method in PIPELINE_STEPS}
PIPELINE_TARGETS = tuple(name for name, _ in PIPELINE_STEPS)
from utils.tweet_to_markdown import fetch_tweet_markdown
from utils.x_likes_fetcher import fetch_likes_with_state


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
        """Fetch recent likes from X and generate Markdown in Incoming/."""
        try:
            urls = self._fetch_like_urls()
        except Exception as exc:
            print(f"🐦 No se pudieron leer los likes de X: {exc}")
            return []

        if not urls:
            print("🐦 No hay nuevos tweets en tus likes")
            return []

        processed_urls = self._load_processed_urls()
        processed_set = set(processed_urls)
        fresh_urls = [url for url in urls if url not in processed_set]

        if not fresh_urls:
            print("🐦 No hay nuevos likes pendientes (todo está ya procesado).")
            return []

        generated: List[Path] = []
        written_urls: List[str] = []

        for url in fresh_urls:
            try:
                markdown, filename = fetch_tweet_markdown(
                    url,
                    # Use storage_state to avoid X's login wall.
                    storage_state=cfg.TWEET_LIKES_STATE,
                )
            except Exception as exc:
                print(f"❌ Error procesando {url}: {exc}")
                continue

            destination = self._unique_destination(self.incoming / filename)
            destination.write_text(markdown, encoding="utf-8")
            generated.append(destination)
            written_urls.append(url)
            print(f"🐦 Tweet guardado como {destination.name}")

        if written_urls:
            self._append_processed_urls(written_urls)

        return generated

    def _unique_destination(self, target: Path) -> Path:
        """Generate a unique name to avoid overwriting existing files."""
        return unique_path(target)

    def _fetch_like_urls(self) -> List[str]:
        if not cfg.TWEET_LIKES_STATE:
            raise RuntimeError("Configura TWEET_LIKES_STATE con el storage_state exportado de X.")
        last_processed = self._last_processed_tweet_url()
        urls, stop_found, _ = fetch_likes_with_state(
            cfg.TWEET_LIKES_STATE,
            likes_url=cfg.TWEET_LIKES_URL,
            max_tweets=cfg.TWEET_LIKES_MAX,
            stop_at_url=last_processed,
            headless=True,
        )
        if last_processed and not stop_found:
            print("⚠️  No se encontró la última URL procesada en los likes; revisa el límite TWEET_LIKES_MAX.")
        return urls

    def _last_processed_tweet_url(self) -> Optional[str]:
        lines = self._load_processed_urls()
        if not lines:
            return None
        return lines[0]

    def _load_processed_urls(self) -> List[str]:
        path = self.tweets_processed
        if not path.exists():
            return []
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
        return [line for line in lines if line]

    def _append_processed_urls(self, urls: List[str]) -> None:
        path = self.tweets_processed
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = self._load_processed_urls()
        # Prepend new URLs (newest first).
        all_urls = list(urls) + [u for u in existing if u not in urls]
        path.write_text("\n".join(all_urls) + "\n", encoding="utf-8")

    def process_podcasts(self) -> List[Path]:
        """Process podcast files with the unified processor."""
        # Use the unified processor for the whole podcasts pipeline.
        return self._run_and_remember(self.podcast_processor.process_podcasts)
    
    def process_instapaper_posts(self) -> List[Path]:
        """Process Instapaper web posts with the unified pipeline."""
        # Use the unified processor for the whole Instapaper pipeline.
        moved_posts = self.instapaper_processor.process_instapaper_posts()

        # Auto-bump: only HTML marked as "starred" by Instapaper.
        # Note for contributors: an article is considered "starred" if a ⭐ is
        # added at the start of the title in Instapaper. Bumping sets its mtime
        # to the future so it appears at the top of date-ordered listings.
        try:
            from utils import is_instapaper_starred_file
            starred_htmls = [
                f for f in moved_posts
                if f.suffix.lower() in {'.html', '.htm'} and is_instapaper_starred_file(f)
            ]
            if starred_htmls:
                U.bump_files(starred_htmls)
        except Exception:
            # Do not block the pipeline if detection fails.
            pass

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
    
    def process_tweets_pipeline(self, *, log_empty_conversion: bool = True) -> List[Path]:
        """Process the tweet queue and move results to the yearly Tweets folder."""
        generated = self.process_tweet_urls()
        return self._process_tweet_markdown_subset(generated, log_empty=log_empty_conversion)

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
            print("Pipeline completado ✅")
            return True
        except Exception as e:
            print(f"❌ Error en el pipeline: {e}")
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
                print("🐦 No hay nuevos tweets para convertir en HTML")
            return []
        return self._run_and_remember(lambda: self.tweet_processor.process_markdown_subset(files))
    
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
