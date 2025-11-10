from pathlib import Path
from datetime import datetime
import os

# Año por defecto = año actual; override opcional con DOCPIPE_YEAR
YEAR = int(os.getenv("DOCPIPE_YEAR", datetime.now().year))

BASE_DIR = Path("/Users/domingo/⭐️ Documentación")
INCOMING = BASE_DIR / "Incoming"
POSTS_DEST = BASE_DIR / "Posts" / f"Posts {YEAR}"
PDFS_DEST = BASE_DIR / "Pdfs" / f"Pdfs {YEAR}"
PODCASTS_DEST = BASE_DIR / "Podcasts" / f"Podcasts {YEAR}"
PROCESSED_HISTORY = INCOMING / "processed_history.txt"

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
INSTAPAPER_USERNAME = os.environ.get("INSTAPAPER_USERNAME")
INSTAPAPER_PASSWORD = os.environ.get("INSTAPAPER_PASSWORD")

TWEET_EDITOR_URL = os.getenv("TWEET_EDITOR_URL", "https://domingogallardo.com/data/nota.txt")
TWEET_EDITOR_USER = os.getenv("TWEET_EDITOR_USER")
TWEET_EDITOR_PASS = os.getenv("TWEET_EDITOR_PASS")
TWEET_EDITOR_TIMEOUT = int(os.getenv("TWEET_EDITOR_TIMEOUT", "15"))
