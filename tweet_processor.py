#!/usr/bin/env python3
"""
TweetProcessor - Módulo independiente para el procesamiento de archivos de tweets
"""
from pathlib import Path
from typing import List

import utils as U


class TweetProcessor:
    """Procesador especializado para archivos de tweets."""
    
    def __init__(self, incoming_dir: Path, destination_dir: Path):
        self.incoming_dir = incoming_dir
        self.destination_dir = destination_dir
    
    def process_tweets(self) -> List[Path]:
        """Procesa archivos de tweets convirtiéndolos a HTML y moviéndolos."""
        print("🐦 Procesando archivos de tweets...")
        
        # Buscar archivos que empiecen con "Tweets" y sean .md
        tweet_files = [f for f in self.incoming_dir.glob("*.md") 
                      if f.name.startswith("Tweets")]
        
        if not tweet_files:
            print("🐦 No se encontraron archivos de tweets para procesar")
            return []
        
        print(f"🐦 Encontrados {len(tweet_files)} archivo(s) de tweets")
        
        processed_files = []
        
        for md_file in tweet_files:
            try:
                # Convertir MD a HTML
                html_file = self._convert_to_html(md_file)
                if html_file:
                    processed_files.append(html_file)
                    
            except Exception as e:
                print(f"❌ Error procesando {md_file}: {e}")
        
        # Mover archivos HTML y MD al destino
        all_files_to_move = []
        for html_file in processed_files:
            # Añadir HTML
            all_files_to_move.append(html_file)
            # Añadir MD original correspondiente
            md_file = html_file.with_suffix('.md')
            if md_file.exists():
                all_files_to_move.append(md_file)
        
        if all_files_to_move:
            moved_files = self._move_files_with_replacement(all_files_to_move, self.destination_dir)
            
            if moved_files:
                print(f"🐦 {len(moved_files)} archivo(s) de tweets movidos a {self.destination_dir}")
            
            return moved_files
        
        return []
    
    def _convert_to_html(self, md_file: Path) -> Path | None:
        """Convierte un archivo Markdown de tweets a HTML."""
        try:
            html_file = md_file.with_suffix('.html')
            
            # Leer contenido Markdown
            md_text = md_file.read_text(encoding="utf-8")
            
            # Convertir a HTML y extraer el cuerpo
            body_content = U.markdown_to_html_body(md_text)

            # Crear HTML completo con estructura mínima
            full_html = self._wrap_html(md_file.stem, body_content)
            
            # Escribir archivo HTML
            html_file.write_text(full_html, encoding="utf-8")
            
            print(f"✅ Convertido a HTML: {html_file.name}")
            return html_file
            
        except Exception as e:
            print(f"❌ Error convirtiendo {md_file}: {e}")
            return None
    

    def _wrap_html(self, title: str, body: str) -> str:
        """Crea un documento HTML completo con título y estilos básicos."""
        return U.wrap_html(title, body, "#1DA1F2")
    
    def _move_files_with_replacement(self, files: List[Path], dest: Path) -> List[Path]:
        """Mueve archivos al destino, reemplazando archivos existentes con el mismo nombre."""
        import shutil
        
        dest.mkdir(parents=True, exist_ok=True)
        moved = []
        
        for f in files:
            new_path = dest / f.name
            
            # Si el archivo de destino ya existe, eliminarlo primero
            if new_path.exists():
                print(f"🔄 Reemplazando archivo existente: {new_path.name}")
                new_path.unlink()  # Eliminar archivo existente
            
            # Mover el nuevo archivo
            shutil.move(str(f), new_path)
            moved.append(new_path)

        return moved
