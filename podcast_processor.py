#!/usr/bin/env python3
"""
PodcastProcessor - Módulo unificado para el procesamiento completo de podcasts de Snipd
"""
from __future__ import annotations
import re
import argparse
import markdown
import os
from pathlib import Path
from typing import List, Iterable

import utils as U


class PodcastProcessor:
    """Procesador unificado para el pipeline completo de podcasts de Snipd."""
    
    def __init__(self, incoming_dir: Path, destination_dir: Path):
        self.incoming_dir = incoming_dir
        self.destination_dir = destination_dir
        
        # Patrones para clean_snip
        self.hr_pattern = re.compile(r"^\s*([\-*_]\s*){3,}$")    # ---  ***  ___
        self.summary_tag = re.compile(r"<summary>(.*?)</summary>", re.IGNORECASE | re.DOTALL)
        self.snip_link = re.compile(r"🎧\s*\[[^\]]*\]\((https://share\.snipd\.com/[^)]+)\)")
    
    def process_podcasts(self) -> List[Path]:
        """Ejecuta el pipeline completo de procesamiento de podcasts."""
        podcasts = U.list_podcast_files(self.incoming_dir)
        if not podcasts:
            print("📻 No se encontraron archivos de podcast para procesar")
            return []
        
        print(f"📻 Procesando {len(podcasts)} archivo(s) de podcast...")
        
        try:
            # 1. Limpiar archivos Snipd
            self._clean_snipd_files()
            
            # 2. Convertir Markdown a HTML
            self._convert_markdown_to_html()
            
            # 3. Añadir márgenes
            self._add_margins()
            
            # 4. Renombrar y mover archivos
            renamed_files = U.rename_podcast_files(podcasts)
            moved_files = U.move_files(renamed_files, self.destination_dir)
            
            if moved_files:
                print(f"📻 {len(moved_files)} archivo(s) de podcast movidos a {self.destination_dir}")
            
            return moved_files
            
        except Exception as e:
            print(f"❌ Error en el procesamiento de podcasts: {e}")
            return []
    
    def _clean_snipd_files(self):
        """Limpia archivos Markdown exportados desde Snipd."""
        md_files = list(self.incoming_dir.rglob("*.md"))
        
        # Filtrar solo archivos de podcast
        podcast_files = [f for f in md_files if U.is_podcast_file(f)]
        
        if not podcast_files:
            print("🧹 No se encontraron archivos de podcast para limpiar")
            return
        
        print(f"🧹 Limpiando {len(podcast_files)} archivo(s) de podcast...")
        
        for md_file in podcast_files:
            try:
                text = md_file.read_text(encoding="utf-8", errors="ignore")
                
                # Reemplazar saltos de línea HTML <br/> y <br/>> para quoted text
                text = re.sub(r"<br\s*/?>\s*>\s*", "\n> ", text)  # <br/>>  → nueva línea con "> "
                text = re.sub(r"<br\s*/?>", "\n", text)              # <br/>   → nueva línea simple
                
                # Reemplazar enlaces de audio
                text = self.snip_link.sub(self._replace_snip_link, text)
                
                original_lines = text.splitlines(keepends=True)
                new_lines = self._clean_lines(original_lines)
                
                if new_lines != original_lines:
                    md_file.write_text("".join(new_lines), encoding="utf-8")
                    print(f"🧹 Limpiado: {md_file}")
                    
            except Exception as e:
                print(f"❌ Error limpiando {md_file}: {e}")
    
    def _replace_snip_link(self, match: re.Match[str]) -> str:
        """Devuelve HTML embebido para el enlace del snip."""
        url = match.group(1)
        # Crear botón atractivo que abre en nueva pestaña
        return (
            f'<div style="text-align: center; margin: 10px 0;">\n'
            f'  <a href="{url}" target="_blank" rel="noopener" '
            f'style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); '
            f'color: white; padding: 12px 20px; text-decoration: none; border-radius: 25px; '
            f'font-size: 14px; font-weight: 500; box-shadow: 0 4px 15px rgba(0,0,0,0.2); '
            f'transition: all 0.3s ease;">\n'
            f'    🎧 Reproducir fragmento de audio\n'
            f'  </a>\n'
            f'</div>'
        )
    
    def _clean_lines(self, lines: Iterable[str]) -> list[str]:
        """Aplica reglas de limpieza línea a línea."""
        cleaned: list[str] = []
        for line in lines:
            lower = line.lower()
            
            # Eliminar etiquetas <details> y </details> pero mantener su contenido
            if '<details' in lower:
                continue
            if '</details>' in lower:
                continue
                
            # Convertir <summary> a texto plano (pero eliminar si es solo "Click to expand")
            if '<summary' in lower:
                cleaned_text = self.summary_tag.sub(r"\1", line).strip()
                # Eliminar si el contenido del summary es solo "Click to expand"
                if cleaned_text.lower() != "click to expand":
                    cleaned.append(cleaned_text + "\n")
                continue
            
            # Eliminar reglas horizontales
            if self.hr_pattern.match(line):
                continue
            
            cleaned.append(line)
        return cleaned
    
    def _convert_markdown_to_html(self):
        """Convierte archivos Markdown de podcast a HTML."""
        md_files = [p for p in self.incoming_dir.rglob("*.md") 
                   if U.is_podcast_file(p) and not p.with_suffix(".html").exists()]
        
        if not md_files:
            print("🔄 No hay archivos Markdown de podcast pendientes de convertir")
            return
        
        print(f"🔄 Convirtiendo {len(md_files)} archivo(s) de podcast a HTML...")
        
        for md_file in md_files:
            try:
                html_path = md_file.with_suffix(".html")
                
                # No sobrescribir si ya existe
                if html_path.exists():
                    continue
                
                md_text = md_file.read_text(encoding="utf-8")
                html_body = self._md_to_html(md_text)
                full_html = self._wrap_html(md_file.stem, html_body)
                html_path.write_text(full_html, encoding="utf-8")
                
                # Mostrar ruta relativa si es posible
                try:
                    display_path = html_path.relative_to(Path.cwd()) if html_path.is_absolute() else html_path
                except ValueError:
                    display_path = html_path
                print(f"✅ HTML generado: {display_path}")
                
            except Exception as e:
                print(f"❌ Error convirtiendo {md_file}: {e}")
    
    def _md_to_html(self, md_text: str) -> str:
        """Convierte texto Markdown en HTML usando la librería markdown."""
        # Limpiar caracteres problemáticos
        md_text = md_text.replace('\xa0', ' ')  # Non-breaking space
        md_text = md_text.replace('\u2013', '-')  # En dash
        md_text = md_text.replace('\u2014', '-')  # Em dash
        md_text = md_text.replace('\u2018', "'")  # Left single quote
        md_text = md_text.replace('\u2019', "'")  # Right single quote
        md_text = md_text.replace('\u201c', '"')  # Left double quote
        md_text = md_text.replace('\u201d', '"')  # Right double quote
        
        # TODO: Implementar conversión de URLs cuando se resuelva el problema de regex
        # # Convertir URLs de texto plano a enlaces Markdown de forma simple
        # import re
        # # Buscar URLs y convertirlas a enlaces Markdown
        # url_pattern = r'https?://[^\s]+'
        # md_text = re.sub(url_pattern, lambda m: f'[{m.group(0)}]({m.group(0)})', md_text)
        
        html_body = markdown.markdown(
            md_text,
            extensions=[
                "fenced_code",
                "tables", 
                "toc",
            ],
            output_format="html5",
        )
        
        return html_body
    
    def _wrap_html(self, title: str, body: str) -> str:
        """Devuelve un documento HTML con cabecera mínima y UTF-8."""
        return (
            "<!DOCTYPE html>\n"
            "<html>\n<head>\n<meta charset=\"UTF-8\">\n"
            f"<title>{title}</title>\n"
            "</head>\n<body>\n"
            f"{body}\n"
            "</body>\n</html>\n"
        ) 

    def _add_margins(self):
        """Añade márgenes a los archivos HTML de podcast."""
        U.add_margins_to_html_files(self.incoming_dir, file_filter=U.is_podcast_file) 