from pathlib import Path

def test_read_location_has_autoindex(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    cfg = (repo_root / "web" / "nginx.conf").read_text(encoding="utf-8").splitlines()
    inside = False
    autoindex = False
    for line in cfg:
        stripped = line.strip()
        if stripped.startswith("location /read/"):
            inside = True
            continue
        if inside:
            if stripped.startswith("}"):
                break
            if "autoindex" in stripped:
                autoindex = "on" in stripped
            assert "try_files" not in stripped
            assert stripped != "index index.html;"
    assert autoindex
