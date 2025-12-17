from pathlib import Path
import os
from datetime import datetime

DOCPIPE_YEAR_ENV = "DOCPIPE_YEAR"


def _system_year() -> int:
    return datetime.now().year


def get_default_year() -> int:
    """
    Año por defecto del pipeline.

    Prioridad:
    - DOCPIPE_YEAR si está definido
    - Año actual del sistema
    """
    env_value = os.getenv(DOCPIPE_YEAR_ENV)
    if env_value:
        return int(env_value)
    return _system_year()


YEAR = get_default_year()

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
