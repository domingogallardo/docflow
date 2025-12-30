from pathlib import Path

from utils.standalone_snipd_to_markdown import SNIP_INDEX_MARKER, SnipdMarkdownConverter


def test_snipd_converter_splits_and_indexes(tmp_path: Path) -> None:
    content = """# Episodio Uno

## Snips
### [00:01] Primer snip
- Nota inicial

# Episodio Dos

## Snips
### [10:00] Segundo snip
- Otra nota
"""
    input_file = tmp_path / "snipd.md"
    input_file.write_text(content, encoding="utf-8")

    output_dir = tmp_path / "out"
    converter = SnipdMarkdownConverter(input_file, output_dir)
    generated = converter.convert()

    assert len(generated) == 2
    first_content = generated[0].read_text(encoding="utf-8")
    second_content = generated[1].read_text(encoding="utf-8")

    assert generated[0].name == "Episodio Uno.md"
    assert generated[1].name == "Episodio Dos.md"
    assert SNIP_INDEX_MARKER in first_content
    assert "- [[00:01] Primer snip](#snip-01-00-01-primer-snip)" in first_content
    assert "### [10:00] Segundo snip {#snip-01-10-00-segundo-snip}" in second_content


def test_snipd_converter_cleans_snipd_artifacts(tmp_path: Path) -> None:
    content = """# The Fractured Entangled Representation Hypothesis (Kenneth Stanley, Akarsh Kumar)

## Episode metadata
- Episode link: [open in Snipd](https://share.snipd.com/episode/abc123)
<details>
<summary>Show notes</summary>
> Are the AI models you use today imposters?
> The Path Is the Goal.
</details>

## Snips
### [00:42] 📚 Transcript
<details>
<summary>Click to expand</summary>
<blockquote><b>Speaker</b><br/><br/>Content line 1<br/>Content line 2</blockquote>
</details>
- Audio link: 🎧 [Play snip](https://share.snipd.com/snip/abc123)
"""

    input_file = tmp_path / "snipd.md"
    input_file.write_text(content, encoding="utf-8")

    output_dir = tmp_path / "clean"
    generated = SnipdMarkdownConverter(input_file, output_dir).convert()

    assert len(generated) == 1
    output_text = generated[0].read_text(encoding="utf-8")

    assert "<details>" not in output_text
    assert "Click to expand" not in output_text
    assert "## Show notes" in output_text
    assert "Play audio clip" in output_text
    assert "<br/>" not in output_text
    assert SNIP_INDEX_MARKER in output_text
    assert "href=\"https://share.snipd.com/episode/abc123\"" not in output_text
