from pathlib import Path
import os
from datetime import datetime

DOCPIPE_YEAR_ENV = "DOCPIPE_YEAR"
DOCFLOW_BASE_DIR_ENV = "DOCFLOW_BASE_DIR"


def _system_year() -> int:
    return datetime.now().year


def get_default_year() -> int:
    """
    Default year for the pipeline.

    Priority:
    - DOCPIPE_YEAR if set
    - Current system year
    """
    env_value = os.getenv(DOCPIPE_YEAR_ENV)
    if env_value:
        return int(env_value)
    return _system_year()


def _require_path_env(var_name: str) -> Path:
    value = os.getenv(var_name)
    if not value:
        raise RuntimeError(
            f"{var_name} is not set. Define it in ~/.docflow_env before running docflow."
        )
    return Path(value).expanduser()


BASE_DIR = _require_path_env(DOCFLOW_BASE_DIR_ENV)
INCOMING = BASE_DIR / "Incoming"
PROCESSED_HISTORY = INCOMING / "processed_history.txt"

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
INSTAPAPER_USERNAME = os.environ.get("INSTAPAPER_USERNAME")
INSTAPAPER_PASSWORD = os.environ.get("INSTAPAPER_PASSWORD")

TWEET_LIKES_STATE = Path(os.getenv("TWEET_LIKES_STATE", "x_state.json")).expanduser()
TWEET_LIKES_URL = os.getenv("TWEET_LIKES_URL", "https://x.com/domingogallardo/likes")
TWEET_LIKES_MAX = int(os.getenv("TWEET_LIKES_MAX", "50"))
