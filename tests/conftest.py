import sys
from pathlib import Path

# Asegura que la raíz del repositorio esté en sys.path para importaciones absolutas
REPO_ROOT = Path(__file__).resolve().parents[1]
repo_root_str = str(REPO_ROOT)
if repo_root_str not in sys.path:
    sys.path.insert(0, repo_root_str)


