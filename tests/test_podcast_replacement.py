"""Episode identity and replacement regressions, without network or AI calls."""
import os

import pytest

from podcast_processor import PodcastProcessor
from utils.markdown_utils import split_front_matter
from utils.podcasts import move_podcast_files, snip_episode_id


def export(episode="episode-a", *, title="Episode", snips=1, transcript=False):
    kind = "podcast_content_type: transcript\n" if transcript else ""
    section = "## Transcript\nFull text" if transcript else "## Snips\n" + "\n".join(
        f"### Snip {i}\nhttps://share.snipd.com/snip/snip-{i}" for i in range(snips)
    )
    return (
        f"---\nsource: podcast\n{kind}---\n# {title}\n\n## Episode metadata\n"
        f"- Show: Show\n- Episode title: {title}\n"
        f"- Episode link: [open in Snipd](https://share.snipd.com/episode/{episode})\n\n{section}\n"
    )


def pair(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.with_suffix(".html").write_text("<html><head></head><body>New HTML</body></html>")
    return [path, path.with_suffix(".html")]


def test_replaces_across_years_preserving_path_identity_and_dates(tmp_path):
    old = tmp_path / "Podcasts/Podcasts 2025/Old title.md"
    pair(old, export().replace("source: podcast", "source: podcast\ndocflow_id: stable-id\ndocflow_ingested_at: 2025-01-01\ndocflow_last_read: 2025-02-01"))
    for p in (old, old.with_suffix(".html")):
        os.utime(p, ns=(1234567890000000000, 1234567890123456789))
    new = tmp_path / "Incoming/Changed title (1).md"
    files = pair(new, export(title="Changed title", snips=3))
    result = move_podcast_files(files, tmp_path / "Podcasts/Podcasts 2026", base_dir=tmp_path)
    assert result == [old, old.with_suffix(".html")]
    assert "### Snip 2" in old.read_text()
    meta, _ = split_front_matter(old.read_text())
    assert meta["docflow_id"] == "stable-id"
    assert meta["docflow_last_read"] == "2025-02-01"
    assert meta["docflow_ingested_at"] == "2025-01-01"
    assert meta["docflow_markdown_path"] == old.relative_to(tmp_path).as_posix()
    for p in result:
        assert p.stat().st_mtime_ns == 1234567890123456789
    assert "stable-id" in old.with_suffix(".html").read_text()
    assert not new.exists()
    assert len(list((tmp_path / "Podcasts").rglob("*.md"))) == 1


@pytest.mark.parametrize("episode", ["different-id", None])
def test_matching_titles_without_matching_ids_do_not_overwrite(tmp_path, episode):
    dest = tmp_path / "Podcasts"
    old = dest / "Same.md"
    pair(old, export())
    text = export(episode or "episode-a")
    if episode is None:
        text = text.replace("- Episode link:", "- Missing link:")
    source = tmp_path / "Incoming/Same.md"
    result = move_podcast_files(pair(source, text), dest, base_dir=tmp_path)
    assert result[0] == dest / "Same (1).md"
    assert old.read_text() == export()


def test_transcript_with_same_episode_is_kept_separately(tmp_path):
    dest = tmp_path / "Podcasts"
    transcript = dest / "Transcript.md"
    original = export(transcript=True)
    pair(transcript, original)
    source = tmp_path / "Incoming/Snips.md"
    result = move_podcast_files(pair(source, export(snips=3)), dest, base_dir=tmp_path)
    assert transcript.read_text() == original
    assert result[0] == dest / "Snips.md"
    assert snip_episode_id(original) is None


def test_missing_html_leaves_previous_pair_untouched(tmp_path):
    old = tmp_path / "Podcasts/Old.md"
    pair(old, export())
    source = tmp_path / "Incoming/New.md"
    source.parent.mkdir()
    source.write_text(export(snips=2))
    with pytest.raises(FileNotFoundError):
        move_podcast_files([source], old.parent, base_dir=tmp_path)
    assert old.read_text() == export()
    assert source.exists()


def test_two_exports_in_one_batch_share_the_same_destination(tmp_path):
    first = tmp_path / "Incoming/First.md"
    second = tmp_path / "Incoming/Second.md"
    files = pair(first, export()) + pair(second, export(snips=3))
    dest = tmp_path / "Podcasts/Podcasts 2026"
    move_podcast_files(files, dest, base_dir=tmp_path)
    assert len(list(dest.glob("*.md"))) == 1
    assert "### Snip 2" in (dest / "First.md").read_text()


def test_pipeline_repeated_canonical_filename_updates_one_pair(tmp_path):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    dest = tmp_path / "Podcasts/Podcasts 2026"
    processor = PodcastProcessor(incoming, dest)
    for count in (1, 3):
        (incoming / "Show - Episode.md").write_text(export(snips=count))
        assert len(processor.process_podcasts()) == 2
    documents = list(dest.glob("*.md"))
    assert len(documents) == 1
    assert "### Snip 2" in documents[0].read_text()
    assert len(list(dest.glob("*.html"))) == 1
