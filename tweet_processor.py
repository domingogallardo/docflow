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
            moved_files = U.move_files(all_files_to_move, self.destination_dir)
            
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
            
            # Convertir a HTML usando las utilidades existentes
            html_body = U.markdown_to_html(md_text)
            
            # Extraer solo el contenido del body
            if '<body>' in html_body and '</body>' in html_body:
                body_content = html_body.split('<body>')[1].split('</body>')[0].strip()
            else:
                body_content = html_body
            
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
        return (
            "<!DOCTYPE html>\n"
            "<html>\n<head>\n<meta charset=\"UTF-8\">\n"
            f"<title>{title}</title>\n"
            "<style>\n"
            f"{U.get_base_css()}"
            "blockquote { border-left: 4px solid #1DA1F2; }\n"
            "a { color: #1DA1F2; }\n"
            "</style>\n"
            "</head>\n<body>\n"
            f"{body}\n"
            "</body>\n</html>\n"
        ) 