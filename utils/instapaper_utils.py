from pathlib import Path
import re


def is_instapaper_starred_file(file_path: Path) -> bool:
    """Detecta si un archivo HTML/MD pertenece a un artículo de Instapaper marcado con estrella."""
    try:
        suffix = file_path.suffix.lower()
        if suffix in {".html", ".htm"}:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            if re.search(r'<meta\s+name=["\']instapaper-starred["\']\s+content=["\']true["\']', content, re.I):
                return True
            if re.search(r'data-instapaper-starred=["\']true["\']', content, re.I):
                return True
            if re.search(r'instapaper_starred:\s*true', content, re.I):
                return True
            return False
        if suffix == ".md":
            head = file_path.read_text(encoding="utf-8", errors="ignore")[:4096]
            return bool(re.search(r'^---\s*\n.*?^instapaper_starred:\s*true\s*$.*?^---\s*$', head, re.I | re.M | re.S) or
                        re.search(r'^instapaper_starred:\s*true\s*$', head, re.I | re.M))
        return False
    except Exception:
        return False
