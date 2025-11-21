#!/usr/bin/env python3
"""
DocumentProcessor - Clase principal para el procesamiento de documentos
"""
from pathlib import Path
from typing import Iterable, List, Optional, Set

import utils as U
import config as cfg
from pdf_processor import PDFProcessor
from instapaper_processor import InstapaperProcessor
from podcast_processor import PodcastProcessor
from image_processor import ImageProcessor
from markdown_processor import MarkdownProcessor
from utils.tweet_to_markdown import fetch_tweet_markdown
from utils.x_likes_fetcher import fetch_likes_with_state


class DocumentProcessor:
    """Procesador principal de documentos con lógica modular y configurable."""
    
    def __init__(self, base_dir: Path, year: int):
        self.base_dir = Path(base_dir)
        self.year = year
        self.incoming = self.base_dir / "Incoming"
        self.posts_dest = self.base_dir / "Posts" / f"Posts {year}"
        self.pdfs_dest = self.base_dir / "Pdfs" / f"Pdfs {year}"
        self.podcasts_dest = self.base_dir / "Podcasts" / f"Podcasts {year}"
        self.images_dest = self.base_dir / "Images" / f"Images {year}"
        self.tweets_dest = self.base_dir / "Tweets" / f"Tweets {year}"
        self.processed_history = self.incoming / "processed_history.txt"
        self.tweets_processed = self.incoming / "tweets_processed.txt"

        self.pdf_processor = PDFProcessor(self.incoming, self.pdfs_dest)
        self.instapaper_processor = InstapaperProcessor(self.incoming, self.posts_dest)
        self.podcast_processor = PodcastProcessor(self.incoming, self.podcasts_dest)
        self.image_processor = ImageProcessor(self.incoming, self.images_dest)
        self.markdown_processor = MarkdownProcessor(self.incoming, self.posts_dest)
        self.tweet_processor = MarkdownProcessor(self.incoming, self.tweets_dest)
        self._history: List[Path] = []
    def process_tweet_urls(self) -> List[Path]:
        """Obtiene los likes recientes desde X y genera Markdown en Incoming/."""
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
            self.generated_tweets = []
            return []

        generated: List[Path] = []
        written_urls: List[str] = []

        for url in fresh_urls:
            try:
                markdown, filename = fetch_tweet_markdown(url)
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
        """Genera un nombre único evitando sobrescribir archivos existentes."""
        if not target.exists():
            return target

        base = target.stem
        suffix = target.suffix
        counter = 1
        while True:
            candidate = target.with_name(f"{base} ({counter}){suffix}")
            if not candidate.exists():
                return candidate
            counter += 1

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
        # Prepend nuevos URLs (más recientes al inicio)
        all_urls = list(urls) + [u for u in existing if u not in urls]
        path.write_text("\n".join(all_urls) + "\n", encoding="utf-8")

    def process_podcasts(self) -> List[Path]:
        """Procesa archivos de podcast con procesador unificado."""
        # Usar el procesador unificado para todo el pipeline de podcasts
        moved_podcasts = self.podcast_processor.process_podcasts()
        self._remember(moved_podcasts)
        return moved_podcasts
    
    def process_instapaper_posts(self) -> List[Path]:
        """Procesa posts web descargados de Instapaper con pipeline unificado."""
        # Usar el procesador unificado para todo el pipeline de Instapaper
        moved_posts = self.instapaper_processor.process_instapaper_posts()

        # Bump automático: solo HTML marcados como "starred" por Instapaper
        # Nota para contribuidores: un artículo se considera "destacado" si en Instapaper
        # se le añade una ⭐ al inicio del título. Al bumpear ajustamos su mtime al futuro
        # para que aparezca arriba en listados ordenados por fecha.
        try:
            from utils import is_instapaper_starred_file
            starred_htmls = [
                f for f in moved_posts
                if f.suffix.lower() in {'.html', '.htm'} and is_instapaper_starred_file(f)
            ]
            if starred_htmls:
                U.bump_files(starred_htmls)
        except Exception:
            # No bloquear el pipeline si falla la detección
            pass

        self._remember(moved_posts)
        return moved_posts
    
    def process_pdfs(self) -> List[Path]:
        """Procesa PDFs usando el procesador especializado."""
        moved_pdfs = self.pdf_processor.process_pdfs()
        self._remember(moved_pdfs)
        return moved_pdfs
    
    def process_images(self) -> List[Path]:
        """Procesa imágenes moviéndolas y generando la galería anual."""
        moved_images = self.image_processor.process_images()
        self._remember(moved_images)
        return moved_images

    def process_markdown(self) -> List[Path]:
        """Procesa archivos Markdown genéricos."""
        moved_markdown = self.markdown_processor.process_markdown()
        self._remember(moved_markdown)
        return moved_markdown
    
    def process_tweets_pipeline(self) -> List[Path]:
        """Procesa la cola de tweets y mueve los resultados a la carpeta anual de Tweets."""
        generated = self.process_tweet_urls()
        return self._process_tweet_markdown_subset(generated)

    def _process_tweet_markdown_subset(self, markdown_files: Iterable[Path]) -> List[Path]:
        files = [Path(path) for path in markdown_files if Path(path).exists()]
        if not files:
            print("🐦 No hay nuevos tweets para convertir en HTML")
            return []
        moved = self.tweet_processor.process_markdown_subset(files)
        self._remember(moved)
        return moved
    
    def register_all_files(self) -> None:
        """Registra todos los archivos procesados en el historial."""
        if self._history:
            U.register_paths(
                self._history,
                base_dir=self.base_dir,
                historial_path=self.processed_history,
            )
            self._history = []
    
    def process_all(self) -> bool:
        """Ejecuta el pipeline completo."""
        try:
            # Fase 0: Descargar tweets pendientes para convertirlos en Markdown
            tweet_sources = self.process_tweet_urls()
            if tweet_sources:
                self._process_tweet_markdown_subset(tweet_sources)

            # Fase 1: Procesar podcasts primero
            self.process_podcasts()

            # Fase 2: Procesar posts de Instapaper (con pipeline completo)
            self.process_instapaper_posts()

            # Fase 3: Procesar PDFs (solo mover, sin pipeline)
            self.process_pdfs()

            # Fase 4: Procesar imágenes (mover y actualizar galería)
            self.process_images()

            # Fase 5: Procesar Markdown genérico
            self.process_markdown()

            # Fase 6: Registrar todo en historial
            self.register_all_files()
            
            print("Pipeline completado ✅")
            return True
        
        except Exception as e:
            print(f"❌ Error en el pipeline: {e}")
            return False 

    def _remember(self, paths: List[Path]) -> None:
        self._history.extend(paths)
