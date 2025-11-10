#!/usr/bin/env python3
"""
DocumentProcessor - Clase principal para el procesamiento de documentos
"""
from pathlib import Path
from typing import List

import utils as U
from pdf_processor import PDFProcessor
from instapaper_processor import InstapaperProcessor
from podcast_processor import PodcastProcessor
from image_processor import ImageProcessor
from markdown_processor import MarkdownProcessor
from utils.tweet_to_markdown import fetch_tweet_markdown


class DocumentProcessorConfig:
    """Configuración para el procesador de documentos."""

    def __init__(self, base_dir: Path, year: int):
        self.base_dir = base_dir
        self.year = year
        self.incoming = base_dir / "Incoming"
        self.posts_dest = base_dir / "Posts" / f"Posts {year}"
        self.pdfs_dest = base_dir / "Pdfs" / f"Pdfs {year}"
        self.podcasts_dest = base_dir / "Podcasts" / f"Podcasts {year}"
        self.images_dest = base_dir / "Images" / f"Images {year}"
        self.processed_history = self.incoming / "processed_history.txt"
        self.tweets_queue = self.incoming / "tweets.txt"


class DocumentProcessor:
    """Procesador principal de documentos con lógica modular y configurable."""
    
    def __init__(self, config: DocumentProcessorConfig):
        self.config = config
        self.pdf_processor = PDFProcessor(self.config.incoming, self.config.pdfs_dest)
        self.instapaper_processor = InstapaperProcessor(self.config.incoming, self.config.posts_dest)
        self.podcast_processor = PodcastProcessor(self.config.incoming, self.config.podcasts_dest)
        self.image_processor = ImageProcessor(self.config.incoming, self.config.images_dest)
        self.markdown_processor = MarkdownProcessor(self.config.incoming, self.config.posts_dest)
        self.moved_podcasts: List[Path] = []
        self.moved_posts: List[Path] = []
        self.moved_pdfs: List[Path] = []
        self.moved_images: List[Path] = []
        self.moved_markdown: List[Path] = []
        self.generated_tweets: List[Path] = []
    def process_tweet_urls(self) -> List[Path]:
        """Procesa la cola Incoming/tweets.txt generando Markdown para cada URL."""
        queue_path = self.config.tweets_queue
        if not queue_path.exists():
            print("🐦 No se encontró Incoming/tweets.txt; nada que procesar")
            return []

        lines = queue_path.read_text(encoding="utf-8").splitlines()
        if not lines:
            print("🐦 tweets.txt está vacío")
            return []

        generated: List[Path] = []
        remaining_lines: List[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                remaining_lines.append(line)
                continue

            try:
                markdown, filename = fetch_tweet_markdown(stripped)
            except Exception as exc:
                print(f"❌ Error procesando {stripped}: {exc}")
                remaining_lines.append(line)
                continue

            destination = self._unique_destination(self.config.incoming / filename)
            destination.write_text(markdown, encoding="utf-8")
            generated.append(destination)
            print(f"🐦 Tweet guardado como {destination.name}")

        self._update_queue_file(queue_path, remaining_lines)
        self.generated_tweets = generated
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

    def _update_queue_file(self, queue_path: Path, remaining_lines: List[str]) -> None:
        """Actualiza tweets.txt eliminando URLs ya procesadas."""
        content = "\n".join(remaining_lines).strip("\n")
        if content:
            queue_path.write_text(content + "\n", encoding="utf-8")
        else:
            queue_path.unlink(missing_ok=True)

    def process_podcasts(self) -> List[Path]:
        """Procesa archivos de podcast con procesador unificado."""
        # Usar el procesador unificado para todo el pipeline de podcasts
        moved_podcasts = self.podcast_processor.process_podcasts()

        self.moved_podcasts = moved_podcasts
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

        self.moved_posts = moved_posts
        return moved_posts
    
    def process_pdfs(self) -> List[Path]:
        """Procesa PDFs usando el procesador especializado."""
        moved_pdfs = self.pdf_processor.process_pdfs()
        self.moved_pdfs = moved_pdfs
        return moved_pdfs
    
    def process_images(self) -> List[Path]:
        """Procesa imágenes moviéndolas y generando la galería anual."""
        moved_images = self.image_processor.process_images()
        self.moved_images = moved_images
        return moved_images

    def process_markdown(self) -> List[Path]:
        """Procesa archivos Markdown genéricos."""
        moved_markdown = self.markdown_processor.process_markdown()
        self.moved_markdown = moved_markdown
        return moved_markdown
    
    def register_all_files(self) -> None:
        """Registra todos los archivos procesados en el historial."""
        all_files = (
            self.moved_posts
            + self.moved_pdfs
            + self.moved_podcasts
            + self.moved_images
            + self.moved_markdown
        )
        if all_files:
            U.register_paths(
                all_files,
                base_dir=self.config.base_dir,
                historial_path=self.config.processed_history,
            )
    
    def process_all(self) -> bool:
        """Ejecuta el pipeline completo."""
        try:
            # Fase 0: Descargar tweets pendientes para convertirlos en Markdown
            self.process_tweet_urls()

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
