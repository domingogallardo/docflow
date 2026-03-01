import os
from pathlib import Path

BASE_DIR_ENV = "DOCFLOW_BASE_DIR"
MIN_WORDS = int(os.getenv("BORRAR_CORTOS_MIN_WORDS", "24"))


def _posts_root() -> Path:
    base_dir = os.getenv(BASE_DIR_ENV)
    if not base_dir:
        raise RuntimeError(
            f"{BASE_DIR_ENV} is not set. Define it in ~/.docflow_env before running this script."
        )
    return Path(base_dir).expanduser() / "Posts"


def contar_palabras_en_archivo(ruta_archivo: Path) -> int:
    with ruta_archivo.open("r", encoding="utf-8") as archivo:
        return len(archivo.read().split())


def eliminar_archivos_cortos_y_html() -> None:
    for ruta_md in _posts_root().rglob("*.md"):
        num_palabras = contar_palabras_en_archivo(ruta_md)
        if num_palabras >= MIN_WORDS:
            continue

        ruta_md.unlink()
        ruta_html = ruta_md.with_suffix(".html")
        if ruta_html.exists():
            ruta_html.unlink()


if __name__ == "__main__":
    eliminar_archivos_cortos_y_html()
