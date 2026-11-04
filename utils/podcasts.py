from pathlib import Path
import os
import re
import shutil

from config import INCOMING
from path_utils import unique_pair
from utils.file_ops import list_files
from utils.markdown_utils import split_front_matter, upsert_front_matter, sync_markdown_html_pair_metadata


def podcast_episode_id(text: str) -> str | None:
    """Read the stable episode ID from Snipd's episode metadata link."""
    match = re.search(
        r"^-\s*Episode link:.*?https://share\.snipd\.com/episode/([\w-]+)",
        text, re.MULTILINE,
    )
    return match.group(1) if match else None


def snip_episode_id(text: str) -> str | None:
    """Exclude full transcripts even when they share the same episode ID."""
    meta, body = split_front_matter(text)
    if meta.get("podcast_content_type") == "transcript":
        return None
    if not re.search(r"^##\s+Snips\s*$", body, re.MULTILINE | re.IGNORECASE):
        return None
    return podcast_episode_id(text)


def replace_podcast_pair(source: Path, target: Path, *, base_dir: Path) -> list[Path]:
    """Install a complete pair, retaining an existing document's identity and dates."""
    source_html = source.with_suffix(".html")
    if not source_html.is_file():
        raise FileNotFoundError(f"Podcast HTML is missing: {source_html}")
    target_html = target.with_suffix(".html")
    existing_stats = {p: p.stat() for p in (target, target_html) if p.exists()}
    text = source.read_text(encoding="utf-8")
    if target.exists():
        old_meta, _ = split_front_matter(target.read_text(encoding="utf-8"))
        preserved = {key: old_meta[key] for key in (
            "docflow_id", "docflow_ingested_at", "docflow_last_read",
        ) if old_meta.get(key)}
        text = upsert_front_matter(text, preserved)
    source.write_text(text, encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(source), str(target))
        shutil.move(str(source_html), str(target_html))
        sync_markdown_html_pair_metadata(target, target_html, base_dir=base_dir)
    finally:
        for path, stat in existing_stats.items():
            if path.exists():
                os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    return [target, target_html]


def move_podcast_files(files: list[Path], destination: Path, *, base_dir: Path) -> list[Path]:
    """Replace snip exports by episode ID across all years of the podcast library."""
    library = destination.parent if re.fullmatch(r"Podcasts \d{4}", destination.name) else destination
    episodes: dict[str, Path] = {}
    for path in sorted(library.rglob("*.md"), key=lambda p: (p.stat().st_mtime_ns, str(p))):
        episode_id = snip_episode_id(path.read_text(encoding="utf-8"))
        if episode_id:
            episodes.setdefault(episode_id, path)
    moved: list[Path] = []
    for source in files:
        if source.suffix != ".md":
            continue
        episode_id = snip_episode_id(source.read_text(encoding="utf-8"))
        target = episodes.get(episode_id) if episode_id else None
        if target is None:
            target, _ = unique_pair(destination / source.name, destination / source.with_suffix(".html").name)
        else:
            print(f"Updating existing podcast episode: {target.name}")
        moved.extend(replace_podcast_pair(source, target, base_dir=base_dir))
        if episode_id:
            episodes[episode_id] = target
    return moved


def is_podcast_file(file_path: Path) -> bool:
    """Detect whether an MD file is a Snipd-exported podcast."""
    try:
        if file_path.suffix.lower() != '.md':
            return False
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        meta, _ = split_front_matter(content)
        return str(meta.get("source", "")).lower() == "podcast"
    except Exception:
        return False


def list_podcast_files(root=None):
    """List all MD files that are podcasts."""
    root = INCOMING if root is None else root
    md_files = list_files({".md"}, root)
    return [f for f in md_files if is_podcast_file(f)]


def extract_episode_title(file_path: Path) -> str | None:
    """Extract the episode title from podcast file metadata."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")

        show_match = re.search(r"- Show:\s*(.+)", content)
        episode_match = re.search(r"- Episode title:\s*(.+)", content)

        if episode_match:
            episode_title = episode_match.group(1).strip()
            show_name = show_match.group(1).strip() if show_match else None

            full_title = f"{show_name} - {episode_title}" if show_name else episode_title

            clean_title = re.sub(r'[<>:"/\\|?*#]', '', full_title)
            clean_title = re.sub(r'\s+', ' ', clean_title).strip()
            return clean_title[:200]
        return None
    except Exception:
        return None


def rename_podcast_files(podcasts: list[Path]) -> list[Path]:
    """Rename podcast files using the episode title."""
    renamed_files = []

    for podcast in podcasts:
        title = extract_episode_title(podcast)
        if not title:
            renamed_files.append(podcast)
            print(f"⚠️  Could not extract title from: {podcast.name}")
            continue

        new_md_path = podcast.parent / f"{title}.md"
        new_html_path = podcast.parent / f"{title}.html"
        new_md_path, new_html_path = unique_pair(new_md_path, new_html_path)

        podcast.rename(new_md_path)
        try:
            original = new_md_path.read_text(encoding="utf-8", errors="ignore")
            updated = upsert_front_matter(original, {"title": title})
            if updated != original:
                new_md_path.write_text(updated, encoding="utf-8")
        except Exception:
            pass
        renamed_files.append(new_md_path)

        html_path = podcast.with_suffix('.html')
        if html_path.exists():
            html_path.rename(new_html_path)
            renamed_files.append(new_html_path)

        print(f"📻 Renamed: {podcast.name} → {new_md_path.name}")

    return renamed_files
