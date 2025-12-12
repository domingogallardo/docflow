from pathlib import Path
import os

# Año por defecto = 2026; override opcional con DOCPIPE_YEAR
DEFAULT_YEAR = 2026
YEAR = int(os.getenv("DOCPIPE_YEAR", DEFAULT_YEAR))

BASE_DIR = Path("/Users/domingo/⭐️ Documentación")
INCOMING = BASE_DIR / "Incoming"
POSTS_DEST = BASE_DIR / "Posts" / f"Posts {YEAR}"
PDFS_DEST = BASE_DIR / "Pdfs" / f"Pdfs {YEAR}"
PODCASTS_DEST = BASE_DIR / "Podcasts" / f"Podcasts {YEAR}"
PROCESSED_HISTORY = INCOMING / "processed_history.txt"

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
INSTAPAPER_USERNAME = os.environ.get("INSTAPAPER_USERNAME")
INSTAPAPER_PASSWORD = os.environ.get("INSTAPAPER_PASSWORD")

TWEET_LIKES_STATE = Path(os.getenv("TWEET_LIKES_STATE", "x_state.json")).expanduser()
TWEET_LIKES_URL = os.getenv("TWEET_LIKES_URL", "https://x.com/domingogallardo/likes")
TWEET_LIKES_MAX = int(os.getenv("TWEET_LIKES_MAX", "50"))
