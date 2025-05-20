import os
import requests
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO
from config import INCOMING

BASE_DIR = INCOMING
MAX_WIDTH = 300

def get_image_width(src):
    try:
        if src.startswith('http'):
            response = requests.get(src, timeout=1)
            img = Image.open(BytesIO(response.content))
        else:
            abs_path = os.path.abspath(src)
            img = Image.open(abs_path)
        return img.width
    except Exception as e:
        print(f"⚠️ No se pudo obtener el ancho de {src}: {e}")
        return None

def process_html_file(file_path):
    try:
        # Siempre UTF-8 directamente
        encoding = 'utf-8'
        with open(file_path, 'r', encoding=encoding) as f:
            soup = BeautifulSoup(f, 'html.parser')

        modified = False
        for img in soup.find_all('img'):
            src = img.get('src')
            if not src:
                continue

            width = get_image_width(src)
            if width and width > MAX_WIDTH:
                img['width'] = str(MAX_WIDTH)
                if 'height' in img.attrs:
                    del img['height']
                modified = True
                print(f"✔ Ajustando: {src} ({width}px → 300px) en {file_path}")

        if modified:
            with open(file_path, 'w', encoding=encoding) as f:
                f.write(str(soup))
            print(f"✅ Fichero actualizado: {file_path}")

    except Exception as e:
        print(f"❌ Error al procesar {file_path}: {e}")

def process_directory(base_path):
    for dirpath, _, filenames in os.walk(base_path):
        for filename in filenames:
            if filename.lower().endswith(('.html', '.htm')):
                full_path = os.path.join(dirpath, filename)
                process_html_file(full_path)

if __name__ == '__main__':
    if not os.path.isdir(BASE_DIR):
        print(f"❌ El directorio no existe: {BASE_DIR}")
    else:
        process_directory(BASE_DIR)