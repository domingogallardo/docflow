import os
import sys
from pathlib import Path

import pytest

# Ensure the repo root is on sys.path for absolute imports.
REPO_ROOT = Path(__file__).resolve().parents[1]
repo_root_str = str(REPO_ROOT)
if repo_root_str not in sys.path:
    sys.path.insert(0, repo_root_str)

# Tests import modules that depend on config.BASE_DIR. Provide a stable default.
os.environ.setdefault("DOCFLOW_BASE_DIR", repo_root_str)

# Also add the 'utils' folder for direct utility imports in tests.
UTILS_DIR = REPO_ROOT / "utils"
utils_dir_str = str(UTILS_DIR)
if utils_dir_str not in sys.path:
    sys.path.insert(0, utils_dir_str)


@pytest.fixture(autouse=True)
def isolate_external_done_links(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent tests from appending to the user's real done-links file."""
    monkeypatch.delenv("DONE_LINKS_FILE", raising=False)
    monkeypatch.delenv("DONE_LINKS_BASE_URL", raising=False)
