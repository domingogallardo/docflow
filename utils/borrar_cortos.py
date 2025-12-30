import os

ruta_base = "/Users/domingo/⭐️ Documentación/Posts/"
min_palabras = 24  # adjust the minimum word count you want here

def contar_palabras_en_archivo(ruta_archivo):
    with open(ruta_archivo, "r", encoding="utf-8") as archivo:
        contenido = archivo.read()
        palabras = contenido.split()
        return len(palabras)

def eliminar_archivos_cortos_y_html():
    for raiz, _, archivos in os.walk(ruta_base):
        for archivo in archivos:
            if archivo.endswith(".md"):
                ruta_md = os.path.join(raiz, archivo)
                num_palabras = contar_palabras_en_archivo(ruta_md)

                if num_palabras < min_palabras:
                    os.remove(ruta_md)

                    nombre_base = os.path.splitext(archivo)[0]
                    ruta_html = os.path.join(raiz, nombre_base + ".html")

                    if os.path.exists(ruta_html):
                        os.remove(ruta_html)

if __name__ == "__main__":
    eliminar_archivos_cortos_y_html()
