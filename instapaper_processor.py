#!/usr/bin/env python3
"""
InstapaperProcessor - Módulo unificado para el procesamiento completo de
artículos de Instapaper.

Nota: el procesador trabaja únicamente con el HTML que entrega
Instapaper. Los recursos externos (imágenes, vídeos, etc.) se enlazan sin
descargarlos, por lo que su disponibilidad depende del servidor de
origen. Si el servicio de origen (por ejemplo, Medium) bloqueó la
descarga cuando Instapaper creó su copia, esas imágenes ya no están
presentes y el pipeline no puede recuperarlas.
"""
from __future__ import annotations
import os
import re
import time
import requests
from openai import OpenAI
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from PIL import Image

from config import INSTAPAPER_USERNAME, INSTAPAPER_PASSWORD, OPENAI_KEY
import utils as U
from title_ai import TitleAIUpdater, rename_markdown_pair


class InstapaperDownloadRegistry:
    """Registro persistente para evitar descargas repetidas de Instapaper."""

    def __init__(self, path: Path):
        self.path = path
        self.entries: Dict[str, Dict[str, object]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return

        try:
            content = self.path.read_text(encoding="utf-8")
        except Exception:
            return

        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split("\t")
            if len(parts) < 2:
                continue

            article_id = parts[0].strip()
            starred_flag = parts[1].strip()
            timestamp = parts[2].strip() if len(parts) > 2 else ""

            if not article_id:
                continue

            self.entries[article_id] = {
                "starred": starred_flag == "1",
                "timestamp": timestamp,
            }

    def should_skip(self, article_id: str, starred_hint: Optional[bool]) -> bool:
        entry = self.entries.get(article_id)
        if not entry:
            return False

        if starred_hint is None:
            return True

        return bool(entry.get("starred")) == starred_hint

    def mark_downloaded(self, article_id: str, starred: bool) -> None:
        timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        self.entries[article_id] = {
            "starred": starred,
            "timestamp": timestamp,
        }
        self._persist()

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for article_id, data in self.entries.items():
            starred_flag = "1" if data.get("starred") else "0"
            timestamp = str(data.get("timestamp") or "")
            lines.append(f"{article_id}\t{starred_flag}\t{timestamp}")

        payload = "\n".join(lines) + ("\n" if lines else "")
        self.path.write_text(payload, encoding="utf-8")


class InstapaperProcessor:
    """Procesador unificado para el pipeline completo de artículos de Instapaper."""
    
    def __init__(self, incoming_dir: Path, destination_dir: Path):
        self.incoming_dir = incoming_dir
        self.destination_dir = destination_dir
        self.session = None
        try:
            self.openai_client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else OpenAI()
        except Exception:
            self.openai_client = None
        self.title_updater = TitleAIUpdater(self.openai_client)
        self.download_registry = InstapaperDownloadRegistry(
            self.incoming_dir / ".instapaper_downloads.txt"
        )


    def process_instapaper_posts(self) -> List[Path]:
        """Ejecuta el pipeline completo de procesamiento de posts de Instapaper."""
        print("📄 Procesando posts de Instapaper...")
        
        try:
            # 1. Descargar artículos de Instapaper
            if not self._download_from_instapaper():
                print("⚠️ No se descargaron artículos de Instapaper, continuando con archivos existentes...")
            
            # 2. Convertir HTML a Markdown
            self._convert_html_to_markdown()
            
            # 3. Corregir codificación HTML
            self._fix_html_encoding()

            # 4. Reducir imágenes
            self._reduce_images_width()

            # 5. Añadir márgenes
            self._add_margins()

            # 6. Generar títulos con IA
            self._update_titles_with_ai()

            # 7. Mover archivos procesados
            posts = self._list_processed_files()
            if posts:
                moved_posts = self._move_files_to_destination(posts)
                print(f"📄 {len(moved_posts)} post(s) movidos a {self.destination_dir}")
                return moved_posts
            else:
                print("📄 No se encontraron posts procesados para mover")
                return []
                
        except Exception as e:
            print(f"❌ Error en el procesamiento de Instapaper: {e}")
            return []
    
    def _download_from_instapaper(self) -> bool:
        """Descarga artículos desde Instapaper."""
        if not INSTAPAPER_USERNAME or not INSTAPAPER_PASSWORD:
            print("❌ Credenciales de Instapaper no configuradas")
            return False
        
        try:
            # Inicializar sesión y login
            self.session = requests.Session()
            login_response = self.session.post("https://www.instapaper.com/user/login", data={
                "username": INSTAPAPER_USERNAME,
                "password": INSTAPAPER_PASSWORD,
                "keep_logged_in": "yes"
            })

            # Verificar login de manera más robusta
            login_successful = True
            
            # Verificar código de estado HTTP
            if login_response.status_code >= 400:
                print(f"❌ Error HTTP {login_response.status_code} - URL incorrecta o servidor no disponible")
                login_successful = False
            
            # Verificar si fuimos redirigidos a la página de login (fallo)
            elif "login" in login_response.url:
                print("❌ Redirigido a página de login - credenciales incorrectas")
                login_successful = False
            
            # Verificar si hay mensajes de error específicos en el contenido
            soup = BeautifulSoup(login_response.text, "html.parser")
            error_messages = soup.find_all(class_="error")
            if error_messages:
                print("❌ Mensajes de error encontrados en la página de login")
                for error in error_messages:
                    print(f"   - {error.get_text().strip()}")
                login_successful = False
            
            # Verificar si hay formulario de login (indica que no estamos logueados)
            login_form = soup.find("form")
            if login_form and "login" in login_form.get("action", ""):
                print("❌ Formulario de login encontrado - no estamos logueados")
                login_successful = False
            
            if not login_successful:
                print("❌ Credenciales de Instapaper incorrectas")
                return False
            
            print("✅ Login en Instapaper exitoso")
            
            # Verificar si hay artículos para descargar
            first_articles, has_more = self._get_article_ids(1)
            if not first_articles:
                print("📚 No hay artículos nuevos en Instapaper para descargar")
                return True  # No es error, simplemente no hay nada
            
            print(f"📚 Iniciando descarga de artículos de Instapaper...")
            
            # Descargar artículos
            page = 1
            failure_log = open("failed.txt", "a+")
            
            while has_more or page == 1:
                print(f"Page {page}")
                if page == 1:
                    articles = first_articles
                else:
                    articles, has_more = self._get_article_ids(page)
                
                for article_id, starred_hint in articles:
                    if self.download_registry.should_skip(article_id, starred_hint):
                        print(f"  {article_id}: ⏭️  ya descargado (sin cambios)")
                        continue

                    print(f"  {article_id}: ", end="")
                    start = time.time()
                    try:
                        file_path, is_starred = self._download_article(article_id)
                        self.download_registry.mark_downloaded(article_id, is_starred)
                        duration = time.time() - start
                        print(f"{round(duration, 2)} seconds")
                    except Exception as e:
                        print("failed!")
                        failure_log.write(f"{article_id}\t{str(e)}\n")
                        failure_log.flush()
                
                page += 1
            
            failure_log.close()
            print("📚 Descarga de Instapaper completada")
            return True
            
        except Exception as e:
            print(f"❌ Error en la descarga de Instapaper: {e}")
            return False

    def _has_star_emoji_prefix(self, s: str) -> bool:
        """Devuelve True si s comienza con el emoji ⭐ (U+2B50) con o sin VS16."""
        if not s:
            return False
        s = s.strip()
        # Solo la estrella emoji '⭐' y su variante con VS16: '⭐️'
        STAR_PREFIXES = ("⭐", "⭐️")
        return s.startswith(STAR_PREFIXES)

    def _strip_star_prefix(self, s: str) -> str:
        """Elimina prefijos de estrella en títulos (⭐, ⭐️, ★, ✪, ✭ + espacios)."""
        if not s:
            return s
        s = s.strip()
        # U+2B50 ⭐, U+FE0F VS16, U+2605 ★, U+272A ✪, U+272D ✭
        return re.sub(r'^\s*(?:[\u2B50\u2605\u272A\u272D]\uFE0F?\s*)+', '', s)

    def _is_starred_from_title_only(self, html: str) -> bool:
        """
        ÚNICA REGLA: starred si y solo si <title> empieza por el emoji ⭐ (con o sin VS16).
        """
        try:
            soup = BeautifulSoup(html, "html.parser")
            page_title = soup.title.string if (soup.title and soup.title.string) else ""
            return self._has_star_emoji_prefix(page_title)
        except Exception:
            return False

    def _get_article_ids(self, page: int = 1) -> Tuple[List[Tuple[str, Optional[bool]]], bool]:
        """Obtiene IDs de artículos de una página con indicación de estrella."""
        url = f"https://www.instapaper.com/u/{page}"
        r = self.session.get(url)

        soup = BeautifulSoup(r.text, "html.parser")
        container = soup.find(id="article_list")
        if not container:
            return [], False

        articles = container.find_all("article")

        items: List[Tuple[str, Optional[bool]]] = []
        for art in articles:
            aid = (art.get("id") or "").replace("article_", "")
            if not aid:
                continue
            items.append((aid, self._is_article_starred_in_list(art)))

        has_more = soup.find(class_="paginate_older") is not None
        return items, has_more

    def _is_article_starred_in_list(self, article_tag) -> Optional[bool]:
        """Detecta si un artículo aparece marcado con estrella en la lista."""
        classes = article_tag.get("class") or []
        if isinstance(classes, str):
            classes = [classes]
        classes = [cls.strip().lower() for cls in classes if cls]
        if "starred" in classes:
            return True

        data_starred = article_tag.get("data-starred")
        if isinstance(data_starred, str):
            normalized = data_starred.strip().lower()
            if normalized in {"1", "true", "yes"}:
                return True
            if normalized in {"0", "false", "no"}:
                return False

        return None

    
    def _download_article(self, article_id: str) -> Tuple[Path, bool]:
        """Descarga un artículo específico.

        Solo se persiste el HTML devuelto por Instapaper. Las etiquetas
        ``<img>`` se conservan con sus URLs originales y **no** se
        descargan los recursos remotos. Esto implica que, si el servidor
        de origen bloquea el hotlinking, las imágenes podrían no
        mostrarse en la copia almacenada.
        """
        r = self.session.get(f"https://www.instapaper.com/read/{article_id}")
        soup = BeautifulSoup(r.text, "html.parser")

        title_el = soup.find(id="titlebar").find("h1")
        raw_title = title_el.getText() if title_el else (soup.title.string if soup.title else f"Instapaper {article_id}")
        title = self._strip_star_prefix(raw_title)  # ← SANEAMOS AQUÍ

        origin = soup.find(id="titlebar").find(class_="origin_line")
        content_node = soup.find(id="story")
        content = content_node.decode_contents() if content_node else ""

        # --- DETECCIÓN DE ESTRELLA (única regla: <title> con ⭐) ---
        is_starred_final = self._is_starred_from_title_only(r.text)

        # --- NOMBRE DE FICHERO ROBUSTO ---
        safe = "".join([c for c in title if c.isalpha() or c.isdigit() or c == " "]).strip()
        if not safe:
            safe = f"Instapaper {article_id}"
        file_name = self._truncate_filename(safe, ".html")
        file_path = self.incoming_dir / file_name

        origin_html = str(origin) if origin else ""
        html_content = self._build_article_html(
            title=title,
            origin_html=origin_html,
            article_id=article_id,
            content=content,
            starred=is_starred_final,
        )

        file_path.write_text(html_content, encoding="utf-8")
        return file_path, is_starred_final

    def _build_article_html(self, *, title: str, origin_html: str, article_id: str, content: str, starred: bool) -> str:
        comment = "<!-- instapaper_starred: true method=read_or_list -->\n" if starred else ""
        html_attrs = ' data-instapaper-starred="true"' if starred else ""
        extra_meta = '<meta name="instapaper-starred" content="true">\n' if starred else ""
        return (
            "<!DOCTYPE html>\n"
            f"{comment}"
            f"<html{html_attrs}>\n"
            "<head>\n"
            '<meta charset="UTF-8">\n'
            f"{extra_meta}"
            f"<title>{title}</title>\n"
            "</head>\n<body>\n"
            f"<h1>{title}</h1>\n"
            f"<div id='origin'>{origin_html} · {article_id}</div>\n"
            f"{content}\n"
            "</body>\n</html>"
        )

    def _truncate_filename(self, name, extension, max_length=200):
        """Trunca nombres de archivo largos."""
        total_length = len(name) + len(extension) + 1
        if total_length > max_length:
            name = name[:max_length - len(extension) - 1]
        return name + extension
    
    def _convert_html_to_markdown(self):
        """Convierte archivos HTML a Markdown."""
        html_files = [
            path for path in U.iter_html_files(self.incoming_dir)
            if not path.with_suffix('.md').exists()
        ]
        
        if not html_files:
            print('📄 No hay archivos HTML pendientes de convertir a Markdown')
            return
        
        print(f'Convirtiendo {len(html_files)} archivos HTML a Markdown')
        
        for html_file in html_files:
            try:
                html_content = html_file.read_text(encoding='utf-8')

                # ¿Está marcado? (solo si existe el meta que pusimos en el HTML)
                is_starred = bool(re.search(
                    r'<meta\s+name=["\']instapaper-starred["\']\s+content=["\']true["\']',
                    html_content, re.I
                ))

                markdown_body = md(html_content, heading_style="ATX")

                markdown_body = re.sub(
                    r'^(#{1,6}\s*)(?:[\u2B50\u2605\u272A\u272D]\uFE0F?\s*)+',
                    r'\1',
                    markdown_body,
                    flags=re.MULTILINE
                )
                
                if is_starred:
                    front_matter = "---\ninstapaper_starred: true\n---\n\n"
                    markdown_content = front_matter + markdown_body
                else:
                    markdown_content = markdown_body  # sin cabecera

                md_file = html_file.with_suffix('.md')
                md_file.write_text(markdown_content, encoding='utf-8')
                print(f'✅ Markdown guardado: {md_file} | starred={is_starred}')
            except Exception as e:
                print(f"❌ Error convirtiendo {html_file}: {e}")
                    
    def _fix_html_encoding(self):
        """Corrige la codificación de archivos HTML."""
        html_files = list(U.iter_html_files(self.incoming_dir))

        if not html_files:
            print('🔧 No hay archivos HTML para procesar codificación')
            return
        
        for html_file in html_files:
            try:
                content = html_file.read_text(encoding='utf-8')
                
                if not self._has_charset_meta(content):
                    new_content = self._insert_charset_meta(content, 'utf-8')
                    html_file.write_text(new_content, encoding='utf-8')
                    print(f"🔧 Codificación actualizada: {html_file}")
            except Exception as e:
                print(f"❌ Error procesando codificación de {html_file}: {e}")

    def _has_charset_meta(self, content):
        """Verifica si el HTML ya tiene meta charset."""
        charset_regex = re.compile(
            r'<meta\s+[^>]*charset\s*=|<meta\s+[^>]*http-equiv=["\']Content-Type["\'][^>]*charset=',
            re.IGNORECASE
        )
        return charset_regex.search(content) is not None
    
    def _insert_charset_meta(self, content, encoding):
        """Inserta meta charset en HTML."""
        head_tag = re.search(r"<head[^>]*>", content, re.IGNORECASE)
        meta_tag = f'<meta charset="{encoding}">\n'

        if head_tag:
            insert_pos = head_tag.end()
            return content[:insert_pos] + "\n" + meta_tag + content[insert_pos:]
        else:
            return meta_tag + content

    def _reduce_images_width(self):
        """Reduce el ancho de imágenes en archivos HTML sin medir remotamente.

        Política: si el HTML declara un width mayor a 300px, lo limitamos a 300px
        y eliminamos height para preservar la proporción. Si no declara width,
        no tocamos el elemento y confiamos en el CSS global
        `img { max-width: 300px; height: auto; }` que se inyecta en _add_margins().
        """
        html_files = list(U.iter_html_files(self.incoming_dir))

        if not html_files:
            print('🖼️  No hay archivos HTML para procesar imágenes')
            return

        max_width = 300
        for html_file in html_files:
            try:
                # Log minimal para identificar en qué archivo se procesa
                print(f"🖼️  Revisando imágenes: {html_file}")
                with open(html_file, 'r', encoding='utf-8') as f:
                    soup = BeautifulSoup(f, 'html.parser')
                
                modified = False
                for img in soup.find_all('img'):
                    src = img.get('src')
                    if not src:
                        continue
                    
                    # Usar el ancho declarado si viene en el HTML; no realizar medición remota
                    width_attr = img.get('width')
                    width = None
                    if width_attr:
                        try:
                            width = int(str(width_attr).strip())
                        except Exception:
                            width = None
                    
                    if width is not None and width > max_width:
                        img['width'] = str(max_width)
                        if 'height' in img.attrs:
                            del img['height']
                        modified = True
                        print(f"🖼️  Ajustando: {src} ({width}px → {max_width}px)")
                
                if modified:
                    with open(html_file, 'w', encoding='utf-8') as f:
                        f.write(str(soup))
                    print(f"✅ Imágenes actualizadas: {html_file}")
                    
            except Exception as e:
                print(f"❌ Error procesando imágenes en {html_file}: {e}")
    
    def _add_margins(self):
        """Añade márgenes a los archivos HTML."""
        U.add_margins_to_html_files(self.incoming_dir)
    
    def _get_image_width(self, src):
        """Obtiene el ancho de una imagen local.

        No realiza ninguna petición de red para imágenes remotas.
        """
        try:
            if src.startswith('http'):
                return None
            abs_path = os.path.abspath(src)
            with Image.open(abs_path) as img:
                return img.width
        except Exception:
            return None

    def _update_titles_with_ai(self):
        """Genera títulos atractivos usando IA para archivos Markdown."""
        md_files = [
            p for p in self.incoming_dir.rglob("*.md")
            if self._is_instapaper_markdown(p)
        ]
        self.title_updater.update_titles(md_files, rename_markdown_pair)

    def _is_instapaper_markdown(self, path: Path) -> bool:
        """Determina si un Markdown proviene de una conversión de Instapaper."""
        return path.with_suffix(".html").exists()

    def _is_instapaper_html(self, path: Path) -> bool:
        """Determina si un HTML pertenece a la exportación de Instapaper."""
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return False
        return "<div id='origin'>" in content or '<div id="origin"' in content
    

    # Nota: la generación de títulos usa title_ai.TitleAIUpdater

    def _list_processed_files(self) -> List[Path]:
        """Lista archivos procesados (HTML y Markdown)."""
        exts = {'.html', '.htm', '.md'}
        processed: List[Path] = []

        for file_path in self.incoming_dir.rglob("*"):
            if not file_path.is_file() or file_path.suffix.lower() not in exts:
                continue

            suffix = file_path.suffix.lower()
            if suffix == '.md' and not self._is_instapaper_markdown(file_path):
                continue
            if suffix in {'.html', '.htm'} and not self._is_instapaper_html(file_path):
                continue

            processed.append(file_path)

        return processed
    
    def _move_files_to_destination(self, files: List[Path]) -> List[Path]:
        """Mueve archivos al destino final."""
        self.destination_dir.mkdir(parents=True, exist_ok=True)
        moved_files = []
        
        for file_path in files:
            dest_path = self.destination_dir / file_path.name
            
            # Evitar sobrescribir archivos existentes
            counter = 1
            while dest_path.exists():
                stem = file_path.stem
                suffix = file_path.suffix
                dest_path = self.destination_dir / f"{stem} ({counter}){suffix}"
                counter += 1
            
            file_path.rename(dest_path)
            moved_files.append(dest_path)
        
        return moved_files 
