#!/usr/bin/env python
"""
update_titles.py
Renombra los artículos Markdown + HTML con un título atractivo
y registra la ruta relativa en Historial.txt
"""
from __future__ import annotations
from pathlib import Path
import re, time, anthropic

# --- configuración central ---
from config import INCOMING, ANTHROPIC_KEY 

# mini-log interno para no procesar dos veces el mismo fichero
DONE_FILE = INCOMING / ".titles_done.txt"

def load_done() -> set[str]:
    if DONE_FILE.exists():
        return set(DONE_FILE.read_text(encoding="utf-8").splitlines())
    return set()

def mark_done(path: Path) -> None:
    with DONE_FILE.open("a", encoding="utf-8") as f:
        f.write(str(path) + "\n")

# ------------------------------------------------------------------
MAX_LEN      = 250
NUM_WORDS    = 500
MAX_BYTES_MD = 1600

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

def first_words(path: Path) -> tuple[str, str]:
    """Devuelve (titulo_actual, texto_inicial)"""
    raw_name      = path.stem[:MAX_LEN]
    words, seen   = [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            words.extend(line.strip().split())
            if len(words) >= NUM_WORDS:
                break
    snippet = " ".join(words[:NUM_WORDS]).encode("utf-8")[:MAX_BYTES_MD].decode("utf-8", "ignore")
    return raw_name, snippet

def detect_lang(text20: str) -> str:
    prompt = f"Identifica si el texto es español o inglés.\n\nTexto:\n{text20}\n\nIdioma:"
    resp   = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=5,
        system="Responde únicamente español o inglés, en minúsculas.",
        messages=[{"role": "user", "content": prompt}]
    )
    return "español" if "español" in resp.content[0].text.lower() else "inglés"

def gen_title(snippet: str, lang: str) -> str:
    prompt = (
        f"Dado el siguiente contenido, genera un título atractivo (máx {MAX_LEN} "
        f"caracteres) en {lang}. Contenido:\n{snippet}\n\nTítulo:"
    )
    resp = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=50,
        system="Devuelve solo el título en una línea. Solo el título, sin ninguna indicación adicional del estilo de 'Aquí tienes un título atractivo'",
        messages=[{"role": "user", "content": prompt}]
    ).content[0].text.strip()

    # limpiar caracteres problemáticos
    title = resp.replace('"', '').lstrip('# ').strip()
    for bad in [":", ".", "/"]:
        title = title.replace(bad, "-")
    return re.sub(r"\s+", " ", title)[:MAX_LEN]

def rename_pair(md_path: Path, new_title: str) -> Path:
    new_base = md_path.with_stem(new_title)
    md_new   = new_base.with_suffix(".md")
    html_old = md_path.with_suffix(".html")
    html_new = new_base.with_suffix(".html")

    md_path.rename(md_new)
    if html_old.exists():
        html_old.rename(html_new)
    return md_new

def main():
    done = load_done()
    md_files = [p for p in INCOMING.rglob("*.md") if str(p) not in done]

    if not md_files:
        print("No hay Markdown nuevos.")
        return

    for md in md_files:
        old_title, snippet = first_words(md)
        lang               = detect_lang(" ".join(snippet.split()[:20]))
        new_title          = gen_title(snippet, lang)

        print(f"📄 {old_title} → {new_title}")

        md_final = rename_pair(md, new_title)
        mark_done(md_final)
        time.sleep(1)

    # Registrar la ruta **relativa definitiva** en Historial.txt
    # (Se hará después de mover los archivos en el driver principal,
    # pero si prefieres hacerlo aquí, úsalo así:)
    # register_paths([md_final])
    print("Títulos actualizados ✅")

if __name__ == "__main__":
    main()