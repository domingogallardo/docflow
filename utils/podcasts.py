from pathlib import Path
import re

from config import INCOMING
from path_utils import unique_pair
from utils.file_ops import list_files
from utils.markdown_utils import split_front_matter


def is_podcast_file(file_path: Path) -> bool:
    """Detect whether an MD file is a Snipd-exported podcast."""
    try:
        if not file_path.suffix.lower() == '.md':
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
        renamed_files.append(new_md_path)

        html_path = podcast.with_suffix('.html')
        if html_path.exists():
            html_path.rename(new_html_path)
            renamed_files.append(new_html_path)

        print(f"📻 Renamed: {podcast.name} → {new_md_path.name}")

    return renamed_files
