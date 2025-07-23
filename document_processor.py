#!/usr/bin/env python3
"""
DocumentProcessor - Clase principal para el procesamiento de documentos con configuración inyectable
"""
from pathlib import Path
from typing import List, Protocol
import subprocess
import sys

import utils as U


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
    
    def process_regular_documents(self) -> tuple[List[Path], List[Path]]:
        """Procesa posts regulares y PDFs."""
        print("📄 Procesando posts regulares y PDFs...")
        
        # Pipeline regular
        if not self._run_regular_pipeline():
            print("❌ Error en el pipeline regular")
            return [], []
        
        # Mover archivos procesados
        posts = U.list_files({".html", ".htm", ".md"}, root=self.config.incoming)
        pdfs = U.list_files({".pdf"}, root=self.config.incoming)
        
        moved_posts = U.move_files(posts, self.config.posts_dest)
        moved_pdfs = U.move_files(pdfs, self.config.pdfs_dest)
        
        self.moved_posts = moved_posts
        self.moved_pdfs = moved_pdfs
        
        return moved_posts, moved_pdfs
    
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
            
            # Fase 2: Procesar posts regulares y PDFs
            self.process_regular_documents()
            
            # Fase 3: Registrar todo en historial
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
    
    def _run_regular_pipeline(self) -> bool:
        """Ejecuta el pipeline regular de posts y PDFs."""
        scripts = [
            "scrape.py",
            "html2md.py",
            "fix_html_encoding.py",
            "reduce_images_width.py",
            "add_margin_html.py",
            "update_titles.py"
        ]
        
        return all(self.script_runner.run_script(script) for script in scripts) 