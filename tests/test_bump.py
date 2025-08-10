#!/usr/bin/env python3
from pathlib import Path

import pytest
import bump as bump_mod


def test_bump_increases_mtime_and_preserves_order(tmp_path: Path):
    file1 = tmp_path / "a.txt"
    file2 = tmp_path / "b.txt"
    file1.write_text("a")
    file2.write_text("b")

    # Registrar mtimes anteriores
    m1_before = file1.stat().st_mtime
    m2_before = file2.stat().st_mtime

    # Ejecutar bump en orden [file1, file2]
    bump_mod.bump([file1, file2])

    m1_after = file1.stat().st_mtime
    m2_after = file2.stat().st_mtime

    # Ambos archivos deben tener mtime mayor que antes
    assert m1_after > m1_before
    assert m2_after > m2_before

    # El segundo debe quedar 1s por encima del primero (tolerancia amplia por FS)
    assert m2_after > m1_after
    assert 0.9 <= (m2_after - m1_after) <= 2.1


def test_add_years_handles_leap_day():
    import datetime as _dt

    leap_day = _dt.datetime(2024, 2, 29)
    result = bump_mod.add_years(leap_day, 1)

    assert result.year == 2025
    assert result.month == 2
    assert result.day == 28


def test_main_without_args_returns_error_code(capsys):
    # Sin argumentos debe devolver código 2 y mostrar uso
    rc = bump_mod.main([])
    assert rc == 2
    captured = capsys.readouterr()
    assert "Uso:" in captured.err


def test_ensure_files_validation(tmp_path: Path):
    # Directorio no es archivo regular
    some_dir = tmp_path / "dir"
    some_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        bump_mod.ensure_files([str(some_dir)])

    # Archivo inexistente
    missing = tmp_path / "missing.txt"
    with pytest.raises(FileNotFoundError):
        bump_mod.ensure_files([str(missing)])

    # Archivo válido
    ok_file = tmp_path / "ok.txt"
    ok_file.write_text("x")
    files = bump_mod.ensure_files([str(ok_file)])
    assert files[0] == ok_file.resolve()


