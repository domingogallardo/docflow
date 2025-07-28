from pathlib import Path
from config import BASE_DIR, INCOMING, HISTORIAL
import os, shutil, logging, re

def list_files(exts, root=INCOMING):
    return [p for p in Path(root).rglob("*") if p.suffix.lower() in exts]

def is_podcast_file(file_path: Path) -> bool:
    """Detecta si un archivo MD es un podcast exportado de Snipd."""
    try:
        if not file_path.suffix.lower() == '.md':
            return False
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        return "Episode metadata" in content and "## Snips" in content
    except Exception:
        return False

def list_podcast_files(root=INCOMING):
    """Lista todos los archivos MD que son podcasts."""
    md_files = list_files({".md"}, root)
    return [f for f in md_files if is_podcast_file(f)]

def extract_episode_title(file_path: Path) -> str | None:
    """Extrae el título del episodio de los metadatos del archivo de podcast."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        
        show_match = re.search(r"- Show:\s*(.+)", content)
        episode_match = re.search(r"- Episode title:\s*(.+)", content)
        
        if episode_match:
            episode_title = episode_match.group(1).strip()
            show_name = show_match.group(1).strip() if show_match else None
            
            # Construir título final
            full_title = f"{show_name} - {episode_title}" if show_name else episode_title
            
            # Limpiar caracteres problemáticos para nombres de archivo
            clean_title = re.sub(r'[<>:"/\\|?*#]', '', full_title)
            clean_title = re.sub(r'\s+', ' ', clean_title).strip()
            return clean_title[:200]  # Limitar longitud
        return None
    except Exception:
        return None

def rename_podcast_files(podcasts: list[Path]) -> list[Path]:
    """Renombra archivos de podcast usando el título del episodio."""
    renamed_files = []
    
    for podcast in podcasts:
        title = extract_episode_title(podcast)
        if not title:
            renamed_files.append(podcast)
            print(f"⚠️  No se pudo extraer título de: {podcast.name}")
            continue
            
        # Generar nombres únicos para MD y HTML
        new_md_path = podcast.parent / f"{title}.md"
        new_html_path = podcast.parent / f"{title}.html"
        
        # Evitar conflictos si ya existe
        counter = 1
        while new_md_path.exists():
            new_md_path = podcast.parent / f"{title} ({counter}).md"
            new_html_path = podcast.parent / f"{title} ({counter}).html"
            counter += 1
        
        # Renombrar archivos
        podcast.rename(new_md_path)
        renamed_files.append(new_md_path)
        
        html_path = podcast.with_suffix('.html')
        if html_path.exists():
            html_path.rename(new_html_path)
            renamed_files.append(new_html_path)
        
        print(f"📻 Renombrado: {podcast.name} → {new_md_path.name}")
    
    return renamed_files

def move_files(files, dest):
    dest.mkdir(parents=True, exist_ok=True)
    moved = []
    for f in files:
        new_path = dest / f.name
        shutil.move(str(f), new_path)
        moved.append(new_path)
    return moved

def register_paths(paths, base_dir: Path = None, historial_path: Path = None):
    """Registra rutas en el historial. Acepta base_dir y historial_path configurables para tests."""
    if not paths:
        return
    
    # Usar valores por defecto si no se especifican (compatibilidad hacia atrás)
    if base_dir is None:
        base_dir = BASE_DIR
    if historial_path is None:
        historial_path = HISTORIAL
    
    lines_new = ["./" + p.relative_to(base_dir).as_posix() + "\n" for p in paths]
    if historial_path.exists():
        old_content = historial_path.read_text(encoding="utf-8")
    else:
        old_content = ""
    historial_path.write_text("".join(lines_new) + old_content, encoding="utf-8")

def setup_logging(level="INFO"):
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )