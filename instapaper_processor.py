#!/usr/bin/env python3
"""
InstapaperProcessor - Módulo unificado para el procesamiento completo de artículos de Instapaper
"""
from __future__ import annotations
import os
import re
import time
import requests
import anthropic
from pathlib import Path
from typing import List
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from PIL import Image
from io import BytesIO

from config import INCOMING, INSTAPAPER_USERNAME, INSTAPAPER_PASSWORD, ANTHROPIC_KEY


class InstapaperProcessor:
    """Procesador unificado para el pipeline completo de artículos de Instapaper."""
    
    def __init__(self, incoming_dir: Path, destination_dir: Path):
        self.incoming_dir = incoming_dir
        self.destination_dir = destination_dir
        self.session = None
        self.done_file = incoming_dir / ".titles_done.txt"
        self.anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        
        # Configuración para títulos
        self.max_title_len = 250
        self.num_words = 500
        self.max_bytes_md = 1600
    
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
            first_ids, has_more = self._get_article_ids(1)
            if not first_ids:
                print("📚 No hay artículos nuevos en Instapaper para descargar")
                return True  # No es error, simplemente no hay nada
            
            print(f"📚 Iniciando descarga de artículos de Instapaper...")
            
            # Descargar artículos
            page = 1
            failure_log = open("failed.txt", "a+")
            
            while has_more or page == 1:
                print(f"Page {page}")
                if page == 1:
                    ids = first_ids
                else:
                    ids, has_more = self._get_article_ids(page)
                
                for article_id in ids:
                    print(f"  {article_id}: ", end="")
                    start = time.time()
                    try:
                        self._download_article(article_id)
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
    
    def _get_article_ids(self, page=1):
        """Obtiene IDs de artículos de una página."""
        r = self.session.get(f"https://www.instapaper.com/u/{page}")
        print(r.url)
        soup = BeautifulSoup(r.text, "html.parser")
        
        articles = soup.find(id="article_list").find_all("article")
        ids = [i["id"].replace("article_", "") for i in articles]
        has_more = soup.find(class_="paginate_older") is not None
        return ids, has_more
    
    def _download_article(self, article_id):
        """Descarga un artículo específico."""
        r = self.session.get(f"https://www.instapaper.com/read/{article_id}")
        soup = BeautifulSoup(r.text, "html.parser")
        
        title = soup.find(id="titlebar").find("h1").getText()
        origin = soup.find(id="titlebar").find(class_="origin_line")
        content = soup.find(id="story").decode_contents()
        
        # Limpiar nombre de archivo
        file_name = "".join([c for c in title if c.isalpha() or c.isdigit() or c == " "]).rstrip()
        file_name = self._truncate_filename(file_name, ".html")
        file_path = self.incoming_dir / file_name
        
        # Crear HTML
        html_content = (
            "<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"UTF-8\">\n"
            f"<title>{title}</title>\n"
            "</head>\n<body>\n"
            f"<h1>{title}</h1>\n"
            f"<div id='origin'>{origin} · {article_id}</div>\n"
            f"{content}\n"
            "</body>\n</html>"
        )
        
        file_path.write_text(html_content, encoding="utf-8")
        return file_path
    
    def _truncate_filename(self, name, extension, max_length=200):
        """Trunca nombres de archivo largos."""
        total_length = len(name) + len(extension) + 1
        if total_length > max_length:
            name = name[:max_length - len(extension) - 1]
        return name + extension
    
    def _convert_html_to_markdown(self):
        """Convierte archivos HTML a Markdown."""
        html_files = list(self.incoming_dir.rglob('*.html'))
        
        # Filtrar archivos que ya tienen versión Markdown
        html_files = [f for f in html_files if not f.with_suffix('.md').exists()]
        
        if not html_files:
            print('📄 No hay archivos HTML pendientes de convertir a Markdown')
            return
        
        print(f'Convirtiendo {len(html_files)} archivos HTML a Markdown')
        
        for html_file in html_files:
            try:
                html_content = html_file.read_text(encoding='utf-8')
                markdown_content = md(html_content, heading_style="ATX")
                
                md_file = html_file.with_suffix('.md')
                md_file.write_text(markdown_content, encoding='utf-8')
                print(f'✅ Markdown guardado: {md_file}')
            except Exception as e:
                print(f"❌ Error convirtiendo {html_file}: {e}")
    
    def _fix_html_encoding(self):
        """Corrige la codificación de archivos HTML."""
        html_files = [f for f in self.incoming_dir.iterdir() 
                     if f.is_file() and f.suffix.lower() in ['.html', '.htm']]
        
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
        """Reduce el ancho de imágenes en archivos HTML."""
        html_files = []
        for dirpath, _, filenames in os.walk(self.incoming_dir):
            for filename in filenames:
                if filename.lower().endswith(('.html', '.htm')):
                    html_files.append(Path(dirpath) / filename)
        
        if not html_files:
            print('🖼️  No hay archivos HTML para procesar imágenes')
            return
        
        max_width = 300
        for html_file in html_files:
            try:
                with open(html_file, 'r', encoding='utf-8') as f:
                    soup = BeautifulSoup(f, 'html.parser')
                
                modified = False
                for img in soup.find_all('img'):
                    src = img.get('src')
                    if not src:
                        continue
                    
                    width = self._get_image_width(src)
                    if width and width > max_width:
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
        import utils as U
        U.add_margins_to_html_files(self.incoming_dir)
    
    def _get_image_width(self, src):
        """Obtiene el ancho de una imagen."""
        try:
            if src.startswith('http'):
                response = requests.get(src, timeout=1)
                img = Image.open(BytesIO(response.content))
            else:
                abs_path = os.path.abspath(src)
                img = Image.open(abs_path)
            return img.width
        except Exception:
            return None
    
    def _update_titles_with_ai(self):
        """Genera títulos atractivos usando IA para archivos Markdown."""
        done = self._load_done_titles()
        md_files = [p for p in self.incoming_dir.rglob("*.md") if str(p) not in done]
        
        if not md_files:
            print("🤖 No hay Markdown nuevos para generar títulos")
            return
        
        print(f"🤖 Generando títulos para {len(md_files)} archivos...")
        
        for md_file in md_files:
            try:
                old_title, snippet = self._extract_content(md_file)
                lang = self._detect_language(" ".join(snippet.split()[:20]))
                new_title = self._generate_title(snippet, lang)
                
                print(f"📄 {old_title} → {new_title}")
                
                md_final = self._rename_file_pair(md_file, new_title)
                self._mark_title_done(md_final)
                time.sleep(1)  # Evitar rate limiting de la API
                
            except Exception as e:
                print(f"❌ Error generando título para {md_file}: {e}")
        
        print("🤖 Títulos actualizados ✅")
    
    def _load_done_titles(self) -> set[str]:
        """Carga archivos ya procesados para títulos."""
        if self.done_file.exists():
            return set(self.done_file.read_text(encoding="utf-8").splitlines())
        return set()
    
    def _mark_title_done(self, path: Path) -> None:
        """Marca un archivo como procesado para títulos."""
        with self.done_file.open("a", encoding="utf-8") as f:
            f.write(str(path) + "\n")
    
    def _extract_content(self, path: Path) -> tuple[str, str]:
        """Extrae título actual y contenido inicial."""
        raw_name = path.stem[:self.max_title_len]
        words = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                words.extend(line.strip().split())
                if len(words) >= self.num_words:
                    break
        snippet = " ".join(words[:self.num_words]).encode("utf-8")[:self.max_bytes_md].decode("utf-8", "ignore")
        return raw_name, snippet
    
    def _detect_language(self, text20: str) -> str:
        """Detecta el idioma del texto."""
        prompt = f"Identifica si el texto es español o inglés.\n\nTexto:\n{text20}\n\nIdioma:"
        resp = self.anthropic_client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=5,
            system="Responde únicamente español o inglés, en minúsculas.",
            messages=[{"role": "user", "content": prompt}]
        )
        return "español" if "español" in resp.content[0].text.lower() else "inglés"
    
    def _generate_title(self, snippet: str, lang: str) -> str:
        """Genera un título atractivo usando IA."""
        prompt = (
            f"Dado el siguiente contenido, genera un título atractivo (máx {self.max_title_len} "
            f"caracteres) en {lang}. Contenido:\n{snippet}\n\nTítulo:"
        )
        resp = self.anthropic_client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=50,
            system="Devuelve solo el título en una línea. Solo el título, sin ninguna indicación adicional del estilo de 'Aquí tienes un título atractivo'. Si detectas el nombre de la newsletter, del autor del post o del repositorio o sitio web en el que se ha publicado el artículo, ponlo como primera parte del título, separándolo del resto con un guión. El nombre del autor del post suele estar al comienzo del artículo.",
            messages=[{"role": "user", "content": prompt}]
        ).content[0].text.strip()
        
        # Limpiar caracteres problemáticos
        title = resp.replace('"', '').replace('#', '').lstrip().strip()
        for bad in [":", ".", "/"]:
            title = title.replace(bad, "-")
        return re.sub(r"\s+", " ", title)[:self.max_title_len]
    
    def _rename_file_pair(self, md_path: Path, new_title: str) -> Path:
        """Renombra archivos .md y .html asociados."""
        new_base = md_path.with_stem(new_title)
        md_new = new_base.with_suffix(".md")
        html_old = md_path.with_suffix(".html")
        html_new = new_base.with_suffix(".html")
        
        md_path.rename(md_new)
        if html_old.exists():
            html_old.rename(html_new)
        return md_new
    
    def _list_processed_files(self) -> List[Path]:
        """Lista archivos procesados listos para mover."""
        return [f for f in self.incoming_dir.rglob("*") 
                if f.is_file() and f.suffix.lower() in ['.html', '.htm', '.md']]
    
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