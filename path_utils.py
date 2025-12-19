from pathlib import Path


def unique_path(path: Path) -> Path:
    """Devuelve una ruta única agregando un sufijo (n) si ya existe."""
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 1
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def unique_pair(
    primary: Path,
    secondary: Path,
    *,
    allow_existing_primary: Path | None = None,
    allow_existing_secondary: Path | None = None,
) -> tuple[Path, Path]:
    """Devuelve un par de rutas únicas con el mismo sufijo numérico si hace falta."""
    def _conflicts(path: Path, allowed: Path | None) -> bool:
        return path.exists() and path != allowed

    if not _conflicts(primary, allow_existing_primary) and not _conflicts(secondary, allow_existing_secondary):
        return primary, secondary

    stem = primary.stem
    parent = primary.parent
    suffix_primary = primary.suffix
    suffix_secondary = secondary.suffix
    counter = 1
    while True:
        candidate_primary = parent / f"{stem} ({counter}){suffix_primary}"
        candidate_secondary = parent / f"{stem} ({counter}){suffix_secondary}"
        if not candidate_primary.exists() and not candidate_secondary.exists():
            return candidate_primary, candidate_secondary
        counter += 1
