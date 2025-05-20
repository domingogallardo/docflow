import os
from bs4 import BeautifulSoup

# Define el margen que deseas aplicar
margin_style = "body { margin-left: 6%; margin-right: 6%; }"

# Ruta base donde se encuentran los archivos HTML
base_dir = "/Users/domingo/⭐️ Documentación/Incoming"

# Recorre los directorios y subdirectorios
for root, dirs, files in os.walk(base_dir):
    for file in files:
        # Verifica que sea un archivo .html o .htm
        if file.endswith(".html") or file.endswith(".htm"):
            file_path = os.path.join(root, file)
            print(f"Procesando archivo: {file_path}")
            # Lee el contenido del archivo gestionando posibles errores de codificación
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    soup = BeautifulSoup(f, 'html.parser')
            except UnicodeDecodeError:
                print(f"⚠️  Problema de codificación en '{file}'. Sustituyendo caracteres inválidos...")
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    soup = BeautifulSoup(f, 'html.parser')
            # Se asume que los archivos HTML ya están normalizados con etiquetas <html>, <head> y <body>
            
            # Busca la etiqueta <head>
            head = soup.head
            if head is None:
                # Si no existe, crea un <head> nuevo y añade el estilo
                head = soup.new_tag("head")
                style_tag = soup.new_tag("style")
                style_tag.string = margin_style
                head.append(style_tag)
                soup.html.insert(0, head)
            else:
                # Si ya hay <head>, verifica si hay una etiqueta <style>
                style_tag = head.find("style")
                if style_tag:
                    # Si hay una etiqueta <style>, añade el margen al final del contenido existente
                    style_tag.string += "\n" + margin_style
                else:
                    # Si no hay <style>, crea una nueva etiqueta <style> con el margen
                    style_tag = soup.new_tag("style")
                    style_tag.string = margin_style
                    head.append(style_tag)
            
            # Sobrescribe el archivo con las modificaciones
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(str(soup))