import random
import webbrowser
from pathlib import Path

# Rutas
posts_txt_path = Path("/Users/domingo/⭐️ Documentación/Posts/Posts.txt")
base_dir = Path("/Users/domingo/⭐️ Documentación/Posts/")

# Leer la lista de ficheros .md
with posts_txt_path.open("r", encoding="utf-8") as f:
    md_relative_paths = [line.strip() for line in f if line.strip().endswith(".md")]

# Filtrar los que tengan un .html correspondiente
html_candidates = []
for md_rel in md_relative_paths:
    md_path = base_dir / md_rel
    html_path = md_path.with_suffix('.html')
    if html_path.exists():
        html_candidates.append(html_path)

# Elegir uno al azar y pedir confirmación
if html_candidates:
    selected = random.choice(html_candidates)
    print(f"\nSe ha seleccionado el fichero:\n  Nombre: {selected.name}\n  Ruta completa: {selected.resolve()}\n")
    response = input("¿Quieres abrirlo en el navegador? (s/n): ").strip().lower()
    if response == "s":
        print(f"Abrir en navegador:\n{selected.resolve()}\n")
        webbrowser.open(selected.resolve().as_uri())
    else:
        print("Operación cancelada por el usuario.")
else:
    print("No se encontró ningún fichero .html correspondiente.")