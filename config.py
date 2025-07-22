from pathlib import Path
from datetime import datetime
import os

# Año por defecto = año actual; override opcional con DOCPIPE_YEAR
YEAR = int(os.getenv("DOCPIPE_YEAR", datetime.now().year))

BASE_DIR   = Path("/Users/domingo/⭐️ Documentación")
INCOMING   = BASE_DIR / "Incoming"
POSTS_DEST = BASE_DIR / "Posts" / f"Posts {YEAR}"
PDFS_DEST  = BASE_DIR / "Pdfs"  / f"Pdfs {YEAR}"
PODCASTS_DEST = BASE_DIR / "Podcasts" / f"Podcasts {YEAR}"
HISTORIAL  = BASE_DIR / "Historial.txt"

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
INSTAPAPER_USERNAME = os.environ.get("INSTAPAPER_USERNAME")
INSTAPAPER_PASSWORD = os.environ.get("INSTAPAPER_PASSWORD")
