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
            md_text = md_file.read_text(encoding="utf-8")
            
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


if __name__ == "__main__":
    convert_md_to_html() 