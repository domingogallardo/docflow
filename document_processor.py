#!/usr/bin/env python3
"""
DocumentProcessor - Clase principal para el procesamiento de documentos con configuración inyectable
"""
from pathlib import Path
from typing import List, Protocol
import subprocess
import sys

import utils as U
from pdf_processor import PDFProcessor
from instapaper_processor import InstapaperProcessor


class ScriptRunner(Protocol):
    """Interfaz para ejecutar scripts, fácil de mockear en tests."""
    def run_script(self, script_name: str, *args) -> bool:
        ...
    def run_script_with_dir(self, script_name: str, directory: str) -> bool:
        ...


class SubprocessScriptRunner:
    """Implementación real usando subprocess."""
    
    def run_script(self, script_name: str, *args) -> bool:
        try:
            subprocess.run([sys.executable, script_name] + list(args), check=True)
            return True
        except subprocess.CalledProcessError:
            return False
    
    def run_script_with_dir(self, script_name: str, directory: str) -> bool:
        return self.run_script(script_name, "--dir", directory)


class DocumentProcessorConfig:
    """Configuración para el procesador de documentos."""
    
    def __init__(self, base_dir: Path, year: int):
        self.base_dir = base_dir
        self.year = year
        self.incoming = base_dir / "Incoming"
        self.posts_dest = base_dir / "Posts" / f"Posts {year}"
        self.pdfs_dest = base_dir / "Pdfs" / f"Pdfs {year}"
        self.podcasts_dest = base_dir / "Podcasts" / f"Podcasts {year}"
        self.historial = base_dir / "Historial.txt"


class DocumentProcessor:
    """Procesador principal de documentos con lógica modular y configurable."""
    
    def __init__(self, config: DocumentProcessorConfig, script_runner: ScriptRunner = None):
        self.config = config
        self.script_runner = script_runner or SubprocessScriptRunner()
        self.pdf_processor = PDFProcessor(self.config.incoming, self.config.pdfs_dest)
        self.instapaper_processor = InstapaperProcessor(self.config.incoming, self.config.posts_dest)
        self.moved_podcasts: List[Path] = []
        self.moved_posts: List[Path] = []
        self.moved_pdfs: List[Path] = []
    
    def process_podcasts(self) -> List[Path]:
        """Procesa archivos de podcast con pipeline especializado."""
        podcasts = U.list_podcast_files(self.config.incoming)
        if not podcasts:
            return []
        
        print(f"📻 Procesando {len(podcasts)} archivo(s) de podcast...")
        
        # Pipeline específico para podcasts
        if not self._run_podcast_pipeline():
            print("❌ Error en el pipeline de podcasts")
            return []
        
        # Renombrar y mover podcasts
        renamed_files = U.rename_podcast_files(podcasts)
        moved_files = U.move_files(renamed_files, self.config.podcasts_dest)
        
        print(f"📻 {len(moved_files)} archivo(s) de podcast movidos a {self.config.podcasts_dest}")
        self.moved_podcasts = moved_files
        return moved_files
    
    def process_instapaper_posts(self) -> List[Path]:
        """Procesa posts web descargados de Instapaper con pipeline unificado."""
        # Usar el procesador unificado para todo el pipeline de Instapaper
        moved_posts = self.instapaper_processor.process_instapaper_posts()
        
        # Aplicar márgenes HTML como paso final (script compartido)
        if moved_posts:
            print("📄 Aplicando márgenes a posts procesados...")
            if not self.script_runner.run_script_with_dir("add_margin_html.py", str(self.config.posts_dest)):
                print("⚠️ Error aplicando márgenes, pero posts ya están procesados")
        
        self.moved_posts = moved_posts
        return moved_posts
    
    def process_pdfs(self) -> List[Path]:
        """Procesa PDFs usando el procesador especializado."""
        moved_pdfs = self.pdf_processor.process_pdfs()
        self.moved_pdfs = moved_pdfs
        return moved_pdfs
    
    def register_all_files(self) -> None:
        """Registra todos los archivos procesados en el historial."""
        all_files = self.moved_posts + self.moved_pdfs + self.moved_podcasts
        if all_files:
            U.register_paths(all_files, base_dir=self.config.base_dir, historial_path=self.config.historial)
    
    def process_all(self) -> bool:
        """Ejecuta el pipeline completo."""
        try:
            # Fase 1: Procesar podcasts primero
            self.process_podcasts()
            
            # Fase 2: Procesar posts de Instapaper (con pipeline completo)
            self.process_instapaper_posts()
            
            # Fase 3: Procesar PDFs (solo mover, sin pipeline)
            self.process_pdfs()
            
            # Fase 4: Registrar todo en historial
            self.register_all_files()
            
            print("Pipeline completado ✅")
            return True
        
        except Exception as e:
            print(f"❌ Error en el pipeline: {e}")
            return False
    
    def _run_podcast_pipeline(self) -> bool:
        """Ejecuta el pipeline específico de podcasts."""
        incoming_str = str(self.config.incoming)
        return (
            self.script_runner.run_script_with_dir("clean_snip.py", incoming_str) and
            self.script_runner.run_script_with_dir("md2html.py", incoming_str) and
            self.script_runner.run_script_with_dir("add_margin_html.py", incoming_str)
        ) 