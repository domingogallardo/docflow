#!/usr/bin/env python3
"""
Convierte archivos Markdown a HTML en el directorio Incoming/
Aplica el mismo procesamiento que los podcasts: conversión + márgenes
"""
import markdown
from pathlib import Path
import config as cfg
import utils as U


def convert_md_to_html():
    """Convierte todos los archivos .md en Incoming/ a HTML."""
    incoming_dir = Path(cfg.INCOMING)
    md_files = list(incoming_dir.glob("*.md"))
    
    if not md_files:
        print("📝 No se encontraron archivos .md para convertir")
        return
    
    print(f"📝 Convirtiendo {len(md_files)} archivo(s) Markdown a HTML...")
    
    for md_file in md_files:
        html_path = md_file.with_suffix(".html")
        
        # Saltar si ya existe el HTML
        if html_path.exists():
            print(f"⏭️  Saltando {md_file.name} (HTML ya existe)")
            continue
        
        try:
            # Leer contenido Markdown
            md_text = md_file.read_text(encoding="utf-8", errors="replace")
            
            # Limpiar solo caracteres realmente problemáticos
            md_text = md_text.replace('\xa0', ' ')  # Non-breaking space problemático
            
            # Convertir URLs de texto plano a enlaces Markdown
            md_text = _convert_urls_to_links(md_text)
            
            # Convertir a HTML usando las mismas extensiones que podcasts
            try:
                html_body = markdown.markdown(
                    md_text,
                    extensions=[
                        "fenced_code",
                        "tables", 
                        "toc",
                    ],
                    output_format="html5",
                )
            except Exception as e:
                print(f"⚠️  Error en conversión markdown, intentando sin extensiones: {e}")
                html_body = markdown.markdown(md_text, output_format="html5")
            
            # Crear HTML completo
            title = md_file.stem
            full_html = (
                "<!DOCTYPE html>\n"
                "<html>\n<head>\n<meta charset=\"UTF-8\">\n"
                f"<title>{title}</title>\n"
                "</head>\n<body>\n"
                f"{html_body}\n"
                "</body>\n</html>\n"
            )
            
            # Guardar HTML
            html_path.write_text(full_html, encoding="utf-8")
            print(f"✅ HTML generado: {html_path.name}")
            
        except Exception as e:
            print(f"❌ Error convirtiendo {md_file.name}: {e}")
            import traceback
            traceback.print_exc()
    
    # Aplicar márgenes a todos los HTML generados
    print("📏 Aplicando márgenes...")
    U.add_margins_to_html_files(incoming_dir)


def _convert_urls_to_links(text: str) -> str:
    """Convierte URLs de texto plano a enlaces Markdown de forma robusta."""
    import re
    
    # Dividir el texto en líneas para procesar línea por línea
    lines = text.split('\n')
    processed_lines = []
    
    for line in lines:
        # Buscar URLs que no estén ya en enlaces Markdown o HTML
        if 'http' in line:
            # Regex simple para encontrar URLs
            url_pattern = r'https?://[^\s\)\]>]+'
            urls = re.findall(url_pattern, line)
            
            for url in urls:
                # Verificar que no esté ya en un enlace Markdown [texto](url) o HTML <a href="url">
                if not (f']({url})' in line or f'[{url}]' in line or f'href="{url}"' in line or f"href='{url}'" in line):
                    # Reemplazar solo la primera ocurrencia que no esté en un enlace
                    line = line.replace(url, f'[{url}]({url})', 1)
        
        processed_lines.append(line)
    
    return '\n'.join(processed_lines)


if __name__ == "__main__":
    convert_md_to_html() 