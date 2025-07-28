from pathlib import Path
from markdownify import markdownify as md
from config import INCOMING 

def listar_archivos_html(ruta_directorio):
    return sorted(Path(ruta_directorio).rglob('*.html'))

def convertir_html_a_markdown(ruta_archivo_html):
    html = Path(ruta_archivo_html).read_text(encoding='utf-8')
    markdown = md(html, heading_style="ATX")
    return markdown

def guardar_markdown(ruta_archivo_original, contenido_md):
    ruta_markdown = ruta_archivo_original.with_suffix('.md')
    ruta_markdown.write_text(contenido_md, encoding='utf-8')
    print(f'✅ Markdown guardado: {ruta_markdown}')

if __name__ == "__main__":
    ruta = INCOMING
    archivos_html = listar_archivos_html(ruta)

    # Filtrar solo los archivos que aún no tienen su versión en Markdown
    archivos_html = [
        archivo for archivo in archivos_html
        if not archivo.with_suffix('.md').exists()
    ]

    lote = 200  # Ajusta aquí el número de archivos a convertir por ejecución
    archivos_a_convertir = archivos_html[:lote]

    if not archivos_a_convertir:
        print('📄 No hay archivos HTML pendientes de convertir a Markdown')
    else:
        print(f'Convirtiendo {len(archivos_a_convertir)} archivos de un total de {len(archivos_html)} pendientes\n')

    for archivo_html in archivos_a_convertir:
        print(f'Procesando archivo: {archivo_html}')
        markdown = convertir_html_a_markdown(archivo_html)
        guardar_markdown(archivo_html, markdown)

    if archivos_a_convertir:
        print('\n🎉 Lote convertido con éxito.')