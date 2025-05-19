import os
import re

# ←←← MODIFICA ESTA RUTA CON LA QUE QUIERAS ANALIZAR
ROOT_PATH = "/Users/domingo/⭐️ Documentación/Incoming"

def has_charset_meta(content):
    charset_regex = re.compile(
        r'<meta\s+[^>]*charset\s*=|<meta\s+[^>]*http-equiv=["\']Content-Type["\'][^>]*charset=',
        re.IGNORECASE
    )
    return charset_regex.search(content) is not None

def insert_charset_meta(content, encoding):
    head_tag = re.search(r"<head[^>]*>", content, re.IGNORECASE)
    meta_tag = f'<meta charset="{encoding}">\n'

    if head_tag:
        insert_pos = head_tag.end()
        return content[:insert_pos] + "\n" + meta_tag + content[insert_pos:]
    else:
        # No <head> encontrado: insertamos el meta al principio del fichero
        return meta_tag + content

def process_html_file(filepath):
    try:
        encoding = 'utf-8'
        with open(filepath, 'r', encoding=encoding) as f:
            content = f.read()

        # Solo actualizar si no hay ya un meta charset
        if not has_charset_meta(content):
            new_content = insert_charset_meta(content, encoding)
            with open(filepath, 'w', encoding=encoding) as f:
                f.write(new_content)
            print(f"Actualizado: {filepath}")
    except Exception as e:
        print(f"Error procesando {filepath}: {e}")

def process_directory(root_path):
    for filename in os.listdir(root_path):
        filepath = os.path.join(root_path, filename)
        if os.path.isfile(filepath) and filename.lower().endswith(('.html', '.htm')):
            process_html_file(filepath)

if __name__ == "__main__":
    process_directory(ROOT_PATH)