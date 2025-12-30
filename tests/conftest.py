import sys
from pathlib import Path

# Ensure the repo root is on sys.path for absolute imports.
REPO_ROOT = Path(__file__).resolve().parents[1]
repo_root_str = str(REPO_ROOT)
if repo_root_str not in sys.path:
    sys.path.insert(0, repo_root_str)

# Also add the 'utils' folder to import 'bump' directly in tests.
UTILS_DIR = REPO_ROOT / "utils"
utils_dir_str = str(UTILS_DIR)
if utils_dir_str not in sys.path:
    sys.path.insert(0, utils_dir_str)

