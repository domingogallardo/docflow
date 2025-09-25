"""Compatibilidad para helpers globales en ``utils.py``.

Este paquete aloja utilidades ejecutables bajo ``utils/`` (por ejemplo,
``utils.build_read_index``). El pipeline principal, sin embargo, espera poder
importar ``import utils as U`` y obtener las funciones definidas en el módulo
raíz ``utils.py``. Al introducir este paquete, la resolución de importaciones de
Python prioriza primero la carpeta antes que el archivo, lo que hacía que
``utils.list_podcast_files`` desapareciese.

Para mantener la compatibilidad y seguir exponiendo las herramientas CLI,
cargamos ``utils.py`` manualmente y re-exportamos sus entidades públicas dentro
del paquete.
"""

from importlib import util as _importlib_util
from pathlib import Path as _Path


_ROOT = _Path(__file__).resolve().parent.parent
_UTILS_PATH = _ROOT / "utils.py"

_spec = _importlib_util.spec_from_file_location("_docflow_utils_module", _UTILS_PATH)
if _spec and _spec.loader:
    _module = _importlib_util.module_from_spec(_spec)
    _spec.loader.exec_module(_module)  # type: ignore[call-arg]

    _public_names = getattr(_module, "__all__", None)
    if _public_names is None:
        _public_names = [name for name in dir(_module) if not name.startswith("_")]

    for _name in _public_names:
        globals()[_name] = getattr(_module, _name)

    __all__ = list(_public_names)
else:  # pragma: no cover - protección defensiva
    raise ImportError(f"No se pudo cargar utils.py desde {_UTILS_PATH}")


del _module, _spec, _public_names, _UTILS_PATH, _ROOT, _importlib_util, _Path
