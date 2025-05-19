import os
from bs4 import BeautifulSoup

# Ruta base donde se encuentran los archivos HTML
base_dir = "/Users/domingo/⭐️ Documentación/Posts/"

def corregir_meta_charset(soup, encoding_detectado):
    meta_tag = soup.find('meta', charset=True)
    if meta_tag:
        if meta_tag['charset'].lower() != encoding_detectado.lower():
            print(f"🔧 Corrigiendo charset en META: '{meta_tag['charset']}' -> '{encoding_detectado}'")
            meta_tag['charset'] = encoding_detectado
    else:
        print(f"➕ Añadiendo etiqueta META con charset '{encoding_detectado}'")
        head = soup.head
        if not head:
            head = soup.new_tag("head")
            soup.html.insert(0, head)
        nueva_meta = soup.new_tag("meta", charset=encoding_detectado)
        head.insert(0, nueva_meta)

for root, dirs, files in os.walk(base_dir):
    for file in files:
        if file.endswith(".html") or file.endswith(".htm"):
            file_path = os.path.join(root, file)
            print(f"\n📄 Procesando archivo: {file_path}")
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    soup = BeautifulSoup(f, 'html.parser')
                encoding_usado = 'utf-8'
            except UnicodeDecodeError:
                with open(file_path, 'r', encoding='windows-1252') as f:
                    soup = BeautifulSoup(f, 'html.parser')
                encoding_usado = 'windows-1252'
                print(f"⚠️  Archivo leído en 'windows-1252' por error de codificación.")

            # Asegurar estructura básica HTML
            if soup.html is None:
                print("🛠️  Añadiendo estructura <html>, <head> y <body> al documento.")
                head_tag = soup.new_tag("head")
                for meta in soup.find_all("meta"):
                    head_tag.append(meta.extract())
                body_tag = soup.new_tag("body")
                body_tag.extend(soup.contents)
                html_tag = soup.new_tag("html")
                html_tag.append(head_tag)
                html_tag.append(body_tag)
                soup.clear()
                soup.append(html_tag)

            # Corregir la etiqueta META
            corregir_meta_charset(soup, encoding_usado)

            # Guardar el archivo normalizado
            with open(file_path, 'w', encoding=encoding_usado) as f:
                f.write(str(soup))

            print("✅ Archivo normalizado y guardado.")