#!/usr/bin/env python3
"""
PodcastProcessor - Módulo unificado para el procesamiento completo de podcasts de Snipd
"""
from __future__ import annotations
import re
import unicodedata
from pathlib import Path
from typing import List, Iterable

import utils as U


SNIP_INDEX_MARKER = "<!-- snip-index -->"


class PodcastProcessor:
    """Procesador unificado para el pipeline completo de podcasts de Snipd."""
    
    def __init__(self, incoming_dir: Path, destination_dir: Path):
        self.incoming_dir = incoming_dir
        self.destination_dir = destination_dir
        
        # Patrones para clean_snip
        self.hr_pattern = re.compile(r"^\s*([\-*_]\s*){3,}$")    # ---  ***  ___
        self.summary_tag = re.compile(r"<summary>(.*?)</summary>", re.IGNORECASE | re.DOTALL)
        self.snip_link = re.compile(r"🎧\s*\[[^\]]*\]\((https://share\.snipd\.com/[^)]+)\)")
        # Encabezados H1 para posibles múltiples episodios en un único archivo
        self.h1_pattern = re.compile(r"^#\s+.+$", re.MULTILINE)
    
    def process_podcasts(self) -> List[Path]:
        """Ejecuta el pipeline completo de procesamiento de podcasts."""
        podcasts = U.list_podcast_files(self.incoming_dir)
        if not podcasts:
            print("📻 No se encontraron archivos de podcast para procesar")
            return []
        
        print(f"📻 Procesando {len(podcasts)} archivo(s) de podcast...")
        
        try:
            # 0. Dividir archivos con múltiples episodios (si los hay)
            self._split_multi_episode_files()

            # Recalcular el conjunto de podcasts tras el split
            podcasts = U.list_podcast_files(self.incoming_dir)

            # 1. Limpiar archivos Snipd
            self._clean_snipd_files()
            
            # 2. Convertir Markdown a HTML
            self._convert_markdown_to_html()
            
            # 3. Renombrar y mover archivos
            renamed_files = U.rename_podcast_files(podcasts)
            moved_files = U.move_files(renamed_files, self.destination_dir)
            
            if moved_files:
                print(f"📻 {len(moved_files)} archivo(s) de podcast movidos a {self.destination_dir}")
            
            return moved_files
            
        except Exception as e:
            print(f"❌ Error en el procesamiento de podcasts: {e}")
            return []

    def _split_multi_episode_files(self):
        """Divide archivos con múltiples episodios (varios H1) en archivos independientes.

        Regla básica: cada episodio comienza con un encabezado de nivel 1 ('# Título').
        Si se detectan 2+ H1 en un archivo que cumple el patrón de Snipd, se crean
        nuevos .md (uno por episodio) y se elimina el archivo original.
        """
        md_files = list(self.incoming_dir.rglob("*.md"))
        # Filtrar solo archivos de podcast
        podcast_files = [f for f in md_files if U.is_podcast_file(f)]

        for md_file in podcast_files:
            try:
                text = md_file.read_text(encoding="utf-8", errors="ignore")
                # Buscar posiciones de los H1
                matches = list(self.h1_pattern.finditer(text))
                if len(matches) <= 1:
                    continue  # nada que dividir

                print(f"✂️  Detectados {len(matches)} episodios en: {md_file.name}. Dividiendo…")

                # Calcular límites de cada bloque
                starts = [m.start() for m in matches]
                ends = starts[1:] + [len(text)]

                new_files: list[Path] = []
                for i, (s, e) in enumerate(zip(starts, ends), start=1):
                    chunk = text[s:e].lstrip()  # limpiar encabezados previos en blanco
                    # Nombre provisional basado en el original
                    base_stem = md_file.stem
                    provisional = md_file.parent / f"{base_stem} - part {i}.md"
                    # Evitar colisiones
                    counter = 1
                    out_path = provisional
                    while out_path.exists():
                        out_path = md_file.parent / f"{base_stem} - part {i} ({counter}).md"
                        counter += 1
                    out_path.write_text(chunk, encoding="utf-8")
                    new_files.append(out_path)

                # Eliminar el archivo original tras crear todos los nuevos
                try:
                    md_file.unlink()
                except Exception:
                    pass  # no bloquear si falla el borrado

                print(f"✂️  Dividido: {md_file.name} → {len(new_files)} archivos")

            except Exception as e:
                print(f"❌ Error dividiendo {md_file}: {e}")
    
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
                original_text = md_file.read_text(encoding="utf-8", errors="ignore")
                text = original_text
                
                # Reemplazar saltos de línea HTML <br/> y <br/>> para quoted text
                text = re.sub(r"<br\s*/?>\s*>\s*", "\n> ", text)  # <br/>>  → nueva línea con "> "
                text = re.sub(r"<br\s*/?>", "\n", text)              # <br/>   → nueva línea simple
                
                # Reemplazar enlaces de audio
                text = self.snip_link.sub(self._replace_snip_link, text)
                
                text = self._lift_show_notes_section(text)
                lines_after = text.splitlines(keepends=True)
                cleaned_lines = self._clean_lines(lines_after)
                final_text = "".join(cleaned_lines)
                final_text = self._add_snip_index(final_text)

                if final_text != original_text:
                    md_file.write_text(final_text, encoding="utf-8")
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
            stripped = line.strip()

            if 'click to expand' in stripped.lower():
                continue
            
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

    def _add_snip_index(self, text: str) -> str:
        """Inserta un índice con enlaces a cada snip y añade anchors a sus títulos."""
        match = re.search(r"(##\s+Snips\s*(?:\r?\n)*)", text, flags=re.IGNORECASE)
        if not match:
            return text

        prefix = text[: match.end()]
        rest = text[match.end() :]

        next_section = re.search(r"\n##\s+", rest)
        snip_block = rest[: next_section.start()] if next_section else rest
        suffix = rest[next_section.start() :] if next_section else ""

        if SNIP_INDEX_MARKER in snip_block:
            return text

        heading_pattern = re.compile(
            r"^(?P<prefix>###\s+)(?P<title>.+?)(?P<attrs>\s*\{[^}]*\})?\s*$",
            re.MULTILINE,
        )

        headings: list[tuple[str, str]] = []

        def replace_heading(match: re.Match[str]) -> str:
            title = match.group("title").strip()
            if not title:
                return match.group(0)

            attr_text = match.group("attrs") or ""
            anchor = self._extract_anchor_id(attr_text)

            if not anchor:
                anchor = self._build_snip_anchor(title, len(headings) + 1)
                if attr_text:
                    inner = attr_text.strip()[1:-1].strip()
                    inner = f"{inner} " if inner else ""
                    attr_text = f" {{{inner}#{anchor}}}"
                else:
                    attr_text = f" {{#{anchor}}}"

            headings.append((title, anchor))
            return f"{match.group('prefix')}{title}{attr_text}"

        updated_block = heading_pattern.sub(replace_heading, snip_block)

        if not headings:
            return text

        index_lines = [
            f"- [{title}](#{anchor})"
            for title, anchor in headings
            if anchor
        ]
        if not index_lines:
            return text

        index_block = f"{SNIP_INDEX_MARKER}\n" + "\n".join(index_lines) + "\n\n"
        return prefix + index_block + updated_block + suffix

    def _extract_anchor_id(self, attr_text: str | None) -> str | None:
        """Extrae el identificador #id de un bloque de atributos de Markdown."""
        if not attr_text:
            return None
        match = re.search(r"#([A-Za-z0-9_-]+)", attr_text)
        return match.group(1) if match else None

    def _build_snip_anchor(self, title: str, index: int) -> str:
        """Genera anchors predecibles para los títulos de los snips."""
        slug = self._slugify(title)
        prefix = f"snip-{index:02d}"
        return f"{prefix}-{slug}" if slug else prefix

    def _slugify(self, text: str) -> str:
        """Normaliza títulos a slugs URL-safe."""
        normalized = unicodedata.normalize("NFKD", text)
        ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        ascii_text = ascii_text.lower()
        ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text)
        return ascii_text.strip("-")

    def _lift_show_notes_section(self, text: str) -> str:
        """Convierte bloques <details> en secciones H2 y mueve metadatos posteriores."""
        details_re = re.compile(
            r"<details>\s*<summary>(?P<title>.*?)</summary>(?P<body>.*?)</details>"
            r"(?P<trailing>(?:\s*\n- [^\n]+)*)",
            re.IGNORECASE | re.DOTALL,
        )

        def _repl(match: re.Match[str]) -> str:
            raw_title = match.group("title") or ""
            title = self.summary_tag.sub(r"\1", raw_title).strip()
            if not title:
                title = "Show notes"

            body = (match.group("body") or "").strip()
            trailing = (match.group("trailing") or "").strip()

            parts: list[str] = []
            if trailing:
                parts.append(trailing)

            heading = f"## {title}\n\n{body}\n\n" if body else f"## {title}\n\n"
            parts.append(heading)

            return "\n\n".join(parts)

        return details_re.sub(_repl, text)
    
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
        """Convierte texto Markdown en HTML y devuelve solo el contenido."""
        return U.markdown_to_html_body(md_text)
    
    def _wrap_html(self, title: str, body: str) -> str:
        """Envuelve el contenido en un HTML con estilos y color de podcast."""
        return U.wrap_html(title, body, "#667eea")
