"""Compatibility: re-export utilities from the utils package."""
from pathlib import Path as _Path

# Allow importing submodules when loading this file as the "utils" module.
__path__ = [str(_Path(__file__).resolve().parent / "utils")]

from utils.file_ops import (
    iter_html_files,
    list_files,
    move_files,
    move_files_with_replacement,
    register_paths,
)
from utils.html_tools import (
    add_margins_to_html_files,
    get_article_js_script_tag,
    get_base_css,
    wrap_html,
)
from utils.markdown_utils import (
    clean_duplicate_markdown_links,
    convert_newlines_to_br,
    convert_urls_to_links,
    extract_html_body,
    front_matter_meta_tags,
    markdown_to_html,
    markdown_to_html_body,
    split_front_matter,
)
from utils.podcasts import (
    extract_episode_title,
    is_podcast_file,
    list_podcast_files,
    rename_podcast_files,
)

__all__ = [
    "add_margins_to_html_files",
    "clean_duplicate_markdown_links",
    "convert_newlines_to_br",
    "convert_urls_to_links",
    "extract_episode_title",
    "extract_html_body",
    "front_matter_meta_tags",
    "get_article_js_script_tag",
    "get_base_css",
    "is_podcast_file",
    "iter_html_files",
    "list_files",
    "list_podcast_files",
    "markdown_to_html",
    "markdown_to_html_body",
    "move_files",
    "move_files_with_replacement",
    "register_paths",
    "rename_podcast_files",
    "split_front_matter",
    "wrap_html",
]
del _Path
