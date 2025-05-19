import os
import anthropic
import re
import time

# --------------------------------------------------------------------
# 1) CONSTANTES Y CLIENTE
# --------------------------------------------------------------------
ruta_base = "/Users/domingo/⭐️ Documentación/Incoming/"
max_titulo_longitud = 250
NUM_PALABRAS = 500
MAX_BYTES_CONTENIDO = 1600
ARCHIVO_REGISTRO = "procesados.txt"
BASE_DOC = "/Users/domingo/⭐️ Documentación/"

cliente = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


# --------------------------------------------------------------------
# 2) UTILIDADES DE REGISTRO
# --------------------------------------------------------------------
def cargar_archivos_procesados():
    if not os.path.exists(ARCHIVO_REGISTRO):
        return set()
    with open(ARCHIVO_REGISTRO, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f)

def registrar_archivo_procesado(ruta_archivo):
    # Ruta relativa a la carpeta raíz, precedida de "./"
    rel_path = os.path.relpath(ruta_archivo, start=BASE_DOC)
    with open(ARCHIVO_REGISTRO, "a", encoding="utf-8") as f:
        f.write(f"./{rel_path}\n")


# --------------------------------------------------------------------
# 3) LÓGICA PARA MARKDOWN + HTML (sin cambios)
# --------------------------------------------------------------------
def renombrar_archivos(ruta_actual_md, nuevo_titulo):
    directorio = os.path.dirname(ruta_actual_md)
    nuevo_nombre_base = nuevo_titulo

    ruta_nueva_md   = os.path.join(directorio, f"{nuevo_nombre_base}.md")
    ruta_actual_html = os.path.splitext(ruta_actual_md)[0] + ".html"
    ruta_nueva_html = os.path.join(directorio, f"{nuevo_nombre_base}.html")

    os.rename(ruta_actual_md, ruta_nueva_md)
    if os.path.exists(ruta_actual_html):
        os.rename(ruta_actual_html, ruta_nueva_html)
    return ruta_nueva_md


def obtener_titulo_y_contenido(ruta_archivo):
    nombre_archivo = os.path.splitext(os.path.basename(ruta_archivo))[0]
    titulo_actual  = nombre_archivo[:max_titulo_longitud]

    with open(ruta_archivo, "r", encoding="utf-8") as archivo:
        lineas = archivo.readlines()

    palabras = []
    for linea in lineas:
        if linea.strip():
            palabras.extend(linea.strip().split())
        if len(palabras) >= NUM_PALABRAS:
            break

    contenido_inicial = " ".join(palabras[:NUM_PALABRAS])
    contenido_inicial = contenido_inicial.encode("utf-8")[:MAX_BYTES_CONTENIDO]\
                                           .decode("utf-8", errors="ignore")
    return titulo_actual, contenido_inicial


def detectar_idioma(contenido_inicial):
    contenido_reducido = " ".join(contenido_inicial.split()[:20])
    prompt_idioma = f"""Identifica en qué idioma está escrito el siguiente contenido, responde únicamente con "español" o "inglés":

Contenido:
{contenido_reducido}

Idioma:"""

    respuesta = cliente.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=5,
        system="Eres un experto en identificar idiomas. Responde sólo con el nombre del idioma en minúsculas (español o inglés).",
        messages=[{"role": "user", "content": prompt_idioma}]
    )
    idioma = respuesta.content[0].text.strip().lower()
    return "español" if "español" in idioma else "inglés"


def generar_nuevo_titulo(titulo_actual, contenido_inicial):
    idioma = detectar_idioma(contenido_inicial)
    prompt_titulo = f"""Dado el siguiente contenido de un artículo en Markdown, genera un título atractivo y breve en {idioma}, que resuma el tema principal, incluyendo si es posible el autor y la publicación.

Contenido:
{contenido_inicial}

Título sugerido:"""

    response = cliente.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=50,
        system="Eres un asistente experto en generar títulos claros y atractivos en español o inglés según se indique. Responde una única línea solo con el título.",
        messages=[{"role": "user", "content": prompt_titulo}]
    )

    titulo_generado = response.content[0].text.strip()\
                           .replace('"', '')\
                           .lstrip('# ')\
                           .strip()

    for caracter in [":", ".", "/"]:
        titulo_generado = titulo_generado.replace(caracter, "-")

    titulo_generado = re.sub(r'\s+', ' ', titulo_generado)
    return titulo_generado[:max_titulo_longitud]


# --------------------------------------------------------------------
# 4) CARGAR ESTADO DE PROCESADOS
# --------------------------------------------------------------------
archivos_procesados = cargar_archivos_procesados()


# --------------------------------------------------------------------
# 5) LISTAS DE TRABAJO
# --------------------------------------------------------------------
# 5a) Markdown pendientes
archivos_md = [
    os.path.join(raiz, archivo)
    for raiz, _, archivos in os.walk(ruta_base)
    for archivo in archivos
    if archivo.endswith(".md")
       and os.path.join(raiz, archivo) not in archivos_procesados
]

# 5b) PDFs pendientes  ────────────────────────────────────────────────
archivos_pdf = [
    os.path.join(raiz, archivo)
    for raiz, _, archivos in os.walk(ruta_base)
    for archivo in archivos
    if archivo.lower().endswith(".pdf")
       and os.path.join(raiz, archivo) not in archivos_procesados
]
# --------------------------------------------------------------------


# --------------------------------------------------------------------
# 6) PROCESAR MARKDOWN / HTML (igual que antes)
# --------------------------------------------------------------------
for ruta_md in archivos_md:
    titulo_actual, contenido_inicial = obtener_titulo_y_contenido(ruta_md)
    nuevo_titulo = generar_nuevo_titulo(titulo_actual, contenido_inicial)

    print(f"  🟡 Título actual: {titulo_actual}")
    print(f"  🟢 Nuevo título sugerido: {nuevo_titulo}\n")

    nueva_ruta_md = renombrar_archivos(ruta_md, nuevo_titulo)
    registrar_archivo_procesado(nueva_ruta_md)
    time.sleep(1)


# --------------------------------------------------------------------
# 7) REGISTRAR PDFs PENDIENTES  (sin más cambios)
# --------------------------------------------------------------------
for ruta_pdf in archivos_pdf:
    print(f"  📄 Registrando PDF: {ruta_pdf}")
    registrar_archivo_procesado(ruta_pdf)