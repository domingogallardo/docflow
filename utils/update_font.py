#!/usr/bin/env python3
"""
Actualiza la tipografía de archivos HTML a la fuente del sistema estándar.

Uso:
    python update_font.py <directorio>
    python update_font.py /path/to/html/files

Ejemplo:
    python update_font.py "/Users/domingo/⭐️ Documentación/Posts/Posts 2025"
"""
import sys
import argparse
from pathlib import Path
from bs4 import BeautifulSoup
import re

# Tipografía del sistema que queremos usar
SYSTEM_FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"

def update_font_in_html(html_file: Path) -> bool:
    """
    Actualiza la tipografía en un archivo HTML.
    
    Returns:
        bool: True si se hizo algún cambio, False si no
    """
    try:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        soup = BeautifulSoup(content, 'html.parser')
        changed = False
        
        # Buscar etiquetas <style>
        style_tags = soup.find_all('style')
        
        if style_tags:
            # Actualizar font-family en etiquetas <style> existentes
            for style_tag in style_tags:
                if style_tag.string:
                    css_content = style_tag.string
                    
                    # Buscar y reemplazar font-family existentes
                    font_pattern = r'font-family\s*:\s*[^;]+;?'
                    if re.search(font_pattern, css_content):
                        new_css = re.sub(font_pattern, f'font-family: {SYSTEM_FONT};', css_content)
                        style_tag.string = new_css
                        changed = True
                    else:
                        # Si no hay font-family, añadirlo al body si existe
                        if 'body' in css_content:
                            # Buscar la regla del body y añadir font-family
                            body_pattern = r'(body\s*\{[^}]*)'
                            if re.search(body_pattern, css_content):
                                def add_font_to_body(match):
                                    body_rule = match.group(1)
                                    if body_rule.endswith('{'):
                                        return f"{body_rule} font-family: {SYSTEM_FONT};"
                                    else:
                                        return f"{body_rule} font-family: {SYSTEM_FONT};"
                                
                                new_css = re.sub(body_pattern, add_font_to_body, css_content)
                                style_tag.string = new_css
                                changed = True
        else:
            # No hay etiquetas <style>, crear una nueva
            head = soup.head
            if head is None:
                # Si no hay <head>, crearlo
                head = soup.new_tag("head")
                if soup.html:
                    soup.html.insert(0, head)
                else:
                    # Si no hay <html>, añadir <head> al principio
                    soup.insert(0, head)
            
            # Crear nueva etiqueta <style> con la tipografía
            style_tag = soup.new_tag("style")
            style_tag.string = f"body {{ font-family: {SYSTEM_FONT}; }}"
            head.append(style_tag)
            changed = True
        
        # Guardar cambios si hubo modificaciones
        if changed:
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(str(soup))
            return True
        
        return False
        
    except Exception as e:
        print(f"❌ Error procesando {html_file}: {e}")
        return False

def find_html_files(directory: Path) -> list[Path]:
    """Encuentra todos los archivos HTML en un directorio."""
    html_files = []
    
    if directory.is_file() and directory.suffix.lower() in ['.html', '.htm']:
        # Si es un archivo HTML individual
        html_files.append(directory)
    elif directory.is_dir():
        # Si es un directorio, buscar archivos HTML
        for file_path in directory.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in ['.html', '.htm']:
                html_files.append(file_path)
    
    return html_files

def main():
    parser = argparse.ArgumentParser(
        description="Actualiza la tipografía de archivos HTML a la fuente del sistema"
    )
    parser.add_argument(
        'directory',
        help='Directorio o archivo HTML a procesar'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Mostrar qué archivos se procesarían sin hacer cambios'
    )
    
    args = parser.parse_args()
    
    target_path = Path(args.directory)
    
    if not target_path.exists():
        print(f"❌ Error: El directorio/archivo '{target_path}' no existe")
        sys.exit(1)
    
    # Encontrar archivos HTML
    html_files = find_html_files(target_path)
    
    if not html_files:
        print(f"📄 No se encontraron archivos HTML en '{target_path}'")
        return
    
    print(f"🔍 Encontrados {len(html_files)} archivo(s) HTML")
    print(f"🎨 Tipografía objetivo: {SYSTEM_FONT}")
    
    if args.dry_run:
        print("\n📋 Archivos que se procesarían:")
        for html_file in html_files:
            print(f"  • {html_file}")
        print(f"\n💡 Ejecuta sin --dry-run para aplicar los cambios")
        return
    
    # Procesar archivos
    updated_count = 0
    
    for html_file in html_files:
        try:
            if update_font_in_html(html_file):
                print(f"✅ Actualizado: {html_file.name}")
                updated_count += 1
            else:
                print(f"⏭️  Sin cambios: {html_file.name}")
        
        except Exception as e:
            print(f"❌ Error: {html_file.name} - {e}")
    
    print(f"\n🎉 Procesamiento completado:")
    print(f"   • {updated_count} archivos actualizados")
    print(f"   • {len(html_files) - updated_count} archivos sin cambios")

if __name__ == "__main__":
    main() 