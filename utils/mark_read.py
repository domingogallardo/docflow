"""Marcar como leído (completado) un archivo de /web/public/read.

Uso:
    python utils/mark_read.py [--deploy] RUTA/AL/ARCHIVO.html [...]

Efectos:
  - Prepend (al principio) el nombre del fichero (basename) a
    web/public/read/read_posts.md si no estaba ya.
  - Regenera web/public/read/read.html (usa utils/build_read_index.py).
  - Si pasas --deploy y hay REMOTE_USER/REMOTE_HOST en el entorno,
    ejecuta web/deploy.sh.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from typing import List


def repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def read_dir(root: str) -> str:
    return os.path.join(root, "web", "public", "read")


def load_read_posts(md_path: str) -> List[str]:
    if not os.path.isfile(md_path):
        return []
    out: List[str] = []
    with open(md_path, "r", encoding="utf-8") as f:
        for raw in f:
            s = raw.strip()
            if not s or s.startswith("#"):
                continue
            if s.startswith("- ") or s.startswith("* "):
                s = s[2:].strip()
            out.append(s)
    return out


def prepend_unique_line(md_path: str, line: str) -> bool:
    """Prepend 'line' if not already present (ignora viñetas y espacios)."""
    existing = load_read_posts(md_path)
    if line in existing:
        return False
    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    tmp_path = md_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as w:
        w.write(f"- {line}\n")
        if os.path.isfile(md_path):
            with open(md_path, "r", encoding="utf-8") as r:
                w.write(r.read())
    os.replace(tmp_path, md_path)
    return True


def build_index(root: str) -> None:
    script = os.path.join(root, "utils", "build_read_index.py")
    subprocess.run([sys.executable, script], check=True)


def deploy(root: str) -> None:
    env = os.environ.copy()
    # Permitir cargar variables de .env.deploy si el usuario ejecutó 'set -a; source .env.deploy; set +a'
    if not env.get("REMOTE_USER") or not env.get("REMOTE_HOST"):
        print("ℹ️  REMOTE_USER/REMOTE_HOST no están en el entorno; omito deploy.")
        return
    script = os.path.join(root, "web", "deploy.sh")
    subprocess.run(["bash", script], check=True, env=env)


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description="Marcar como leído (docflow)")
    p.add_argument("paths", nargs="+", help="Ruta(s) a archivo(s) dentro de web/public/read")
    p.add_argument("--deploy", action="store_true", help="Desplegar tras actualizar el índice")
    args = p.parse_args(argv[1:])

    root = repo_root()
    rdir = read_dir(root)
    md_path = os.path.join(rdir, "read_posts.md")

    updated = False
    for pth in args.paths:
        base = os.path.basename(pth)
        abs_selected = os.path.abspath(pth)
        # Validar ubicación: permitir tanto selección dentro de rdir como basename existente en rdir
        in_read_dir = os.path.commonpath([abs_selected, rdir]) == rdir if os.path.exists(abs_selected) else False
        target_exists = os.path.isfile(os.path.join(rdir, base))
        if not in_read_dir and not target_exists:
            print(f"❌ El archivo no está en {rdir} o no existe allí: {pth}")
            continue
        if prepend_unique_line(md_path, base):
            print(f"✓ Marcado como leído: {base}")
            updated = True
        else:
            print(f"✓ Ya estaba en la lista: {base}")

    if updated:
        build_index(root)
        if args.deploy:
            deploy(root)
    else:
        print("ℹ️  Sin cambios en read_posts.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

