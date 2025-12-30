#!/usr/bin/env python3
"""Generate a daily summary from drafts in Pulse/Incoming."""

from __future__ import annotations

import sys
from datetime import datetime
import re
from pathlib import Path
from typing import Iterable, List
from urllib.parse import unquote, urlparse

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency
    OpenAI = None  # type: ignore[assignment]

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import BASE_DIR, OPENAI_KEY

PULSE_DIR = BASE_DIR / "Pulse"
INCOMING_DIR = PULSE_DIR / "Incoming"

SUMMARY_WORD_TARGET = 275
SUMMARY_MODEL = "gpt-5-mini"
SUMMARY_MAX_OUTPUT_TOKENS = 1500
MAX_SUMMARY_INPUT_CHARS = 20000
FALLBACK_LINES = 50

if OpenAI is not None:
    try:
        _OPENAI_CLIENT = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else OpenAI()
    except Exception:
        _OPENAI_CLIENT = None
else:
    _OPENAI_CLIENT = None

_SUMMARY_WARNING_EMITTED = False


def _list_markdown_files() -> list[Path]:
    if not INCOMING_DIR.exists():
        return []
    return sorted(
        (path for path in INCOMING_DIR.glob("*.md") if path.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def _read_url(md_path: Path) -> str:
    candidate = md_path.with_suffix(".url")
    if not candidate.exists():
        return ""
    try:
        with candidate.open("r", encoding="utf-8") as fh:
            first = fh.readline().strip()
            return first
    except UnicodeDecodeError:
        return ""


def _load_markdown_text(md_path: Path) -> str:
    try:
        content = md_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""
    return content


def _original_filename(url: str) -> str:
    if not url:
        return "(Sin título)"
    parsed = urlparse(url)
    path = parsed.path or ""
    if not path:
        return "(Sin título)"
    decoded = unquote(path)
    name = Path(decoded).name
    if not name:
        return "(Sin título)"
    if name.lower().endswith(".html"):
        stripped = Path(name).with_suffix("").name
        return stripped or Path(name).stem
    return name


def _extract_year_from_url(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    decoded = unquote(parsed.path or "")
    for segment in Path(decoded).parts:
        match = re.search(r"(\d{4})", segment)
        if match:
            return match.group(1)
    return None


def _collect_openai_output(resp) -> str:
    text = (getattr(resp, "output_text", "") or "").strip()
    if text:
        return text

    def _collect(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "".join(_collect(item) for item in value)
        if isinstance(value, dict):
            return "".join(
                [
                    str(value.get("text", "")),
                    _collect(value.get("content")),
                    str(value.get("output_text", "")),
                ]
            )
        if hasattr(value, "text"):
            return str(getattr(value, "text", ""))
        if hasattr(value, "content"):
            return _collect(getattr(value, "content"))
        if hasattr(value, "output_text"):
            return str(getattr(value, "output_text", ""))
        return str(value)

    for attr in ("output", "content", "messages"):
        payload = getattr(resp, attr, None)
        if payload:
            text = _collect(payload).strip()
            if text:
                return text
    return ""


def _call_openai(system: str, prompt: str, *, max_tokens: int) -> str:
    if _OPENAI_CLIENT is None:
        raise RuntimeError("Cliente OpenAI no configurado")
    client = _OPENAI_CLIENT
    if hasattr(client, "with_options"):
        client = client.with_options(timeout=45)
    response = client.responses.create(
        model=SUMMARY_MODEL,
        instructions=system,
        input=prompt,
        max_output_tokens=max_tokens,
        reasoning={"effort": "minimal"},
        text={"verbosity": "low"},
    )
    text = _collect_openai_output(response)
    if not text:
        try:
            debug_dump = response.model_dump() if hasattr(response, "model_dump") else repr(response)
        except Exception as exc:
            debug_dump = f"<no dump available: {exc!r}>"
        raise RuntimeError(f"Respuesta vacía de OpenAI. Detalles: {debug_dump}")
    return text


_SPANISH_MARKERS = (
    " el ",
    " la ",
    " los ",
    " las ",
    " de ",
    " que ",
    " una ",
    " un ",
    " por ",
    " para ",
    " no ",
    " si ",
    " del ",
    " al ",
    " con ",
    " más ",
    " también ",
    " como ",
)

_ENGLISH_MARKERS = (
    " the ",
    " and ",
    " that ",
    " with ",
    " from ",
    " have ",
    " has ",
    " this ",
    " there ",
    " about ",
    " which ",
    " more ",
    " into ",
    " without ",
    " where ",
    " when ",
    " would ",
    " could ",
)


def _guess_language(text: str) -> str:
    sample = text.lower()
    accent_count = sum(sample.count(ch) for ch in "áéíóúñ¿¡")
    spanish_score = accent_count * 2
    english_score = 0

    for marker in _SPANISH_MARKERS:
        if marker in sample:
            spanish_score += 1
    for marker in _ENGLISH_MARKERS:
        if marker in sample:
            english_score += 1

    if spanish_score == english_score:
        # Break ties based on extended characters vs pure ASCII.
        non_ascii = sum(1 for ch in sample if ord(ch) > 127)
        if non_ascii > len(sample) * 0.01:
            spanish_score += 1

    if spanish_score >= english_score:
        return "español"
    return "inglés"


def _extract_sections_from_markdown(md_path: Path, max_sections: int = 10) -> List[str]:
    headings: List[str] = []
    try:
        for line in md_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                heading = stripped.lstrip("#").strip()
                if heading:
                    headings.append(heading)
            if len(headings) >= max_sections:
                break
    except UnicodeDecodeError:
        return []
    return headings


def _fallback_summary_and_sections(md_path: Path) -> tuple[List[str], List[str]]:
    summary_lines = _fallback_lines(md_path, FALLBACK_LINES)
    sections = _extract_sections_from_markdown(md_path)
    sections = _ensure_sections(sections, md_path.stem, summary_lines)
    return summary_lines, sections


def _parse_summary_sections(text: str) -> tuple[List[str], List[str]]:
    cleaned = text.replace("\r\n", "\n").strip()
    if not cleaned:
        return [], []

    summary_lines: List[str] = []
    sections: List[str] = []
    in_sections = False
    bullet_prefixes = ("- ", "* ", "• ")

    def _clean_section_heading(value: str) -> str:
        trimmed = value.strip()
        trimmed = re.sub(r"^[#•\-\s]+", "", trimmed)
        # Remove heading-level prefixes like "H2", "H3:", "H1 -", etc.
        trimmed = re.sub(r"^(?:H|h)[1-6]\s*[.:)\-–—]*\s*", "", trimmed)
        trimmed = re.sub(r"^(?:Level\s*\d+)\s*[:)\-–—]*\s*", "", trimmed)
        trimmed = trimmed.strip("• ").strip()
        trimmed = trimmed.rstrip("|").rstrip().rstrip(".").strip()
        return trimmed

    for raw_line in cleaned.split("\n"):
        line = raw_line.strip()
        if not line:
            if not in_sections:
                # Keep paragraph separation.
                if summary_lines and summary_lines[-1] != "":
                    summary_lines.append("")
            continue

        lowered = line.lower()
        if lowered.startswith("secciones:"):
            in_sections = True
            continue

        section_text = None
        for prefix in bullet_prefixes:
            if line.startswith(prefix):
                section_text = line[len(prefix) :]
                break

        if section_text is not None:
            in_sections = True
            section = _clean_section_heading(section_text)
            if section:
                sections.append(section)
            continue

        if in_sections:
            if sections:
                combined = f"{sections[-1]} {line}".strip()
                sections[-1] = _clean_section_heading(combined)
            else:
                sections.append(_clean_section_heading(line))
        else:
            summary_lines.append(line)

    # Remove possible trailing blanks.
    while summary_lines and summary_lines[-1] == "":
        summary_lines.pop()

    return summary_lines, sections


def _normalize_label(value: str) -> str:
    return re.sub(r"\W+", "", value or "").lower()


def _deduplicate_sections(sections: List[str], title: str) -> List[str]:
    normalized_title = _normalize_label(title)
    seen: set[str] = set()
    cleaned: List[str] = []
    for raw in sections:
        cleaned_item = raw.strip().strip("•")
        if not cleaned_item:
            continue
        normalized_item = _normalize_label(cleaned_item)
        if not normalized_item:
            continue
        if normalized_item == normalized_title:
            continue
        if normalized_item in seen:
            continue
        seen.add(normalized_item)
        cleaned.append(cleaned_item)
    return cleaned


def _generate_topics_from_summary(summary_lines: List[str], count: int) -> List[str]:
    text = " ".join(line for line in summary_lines if line).strip()
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    topics: List[str] = []
    seen: set[str] = set()
    for sentence in sentences:
        raw = sentence.strip()
        if not raw:
            continue
        core = re.sub(r"[\-–—•#]+", " ", raw).strip()
        if not core:
            continue
        words = core.split()
        preview = " ".join(words[:6]).rstrip(",;:.-").strip()
        if len(words) > 6:
            preview = f"{preview}…"
        normalized = _normalize_label(preview)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        topics.append(preview)
        if len(topics) >= count:
            break
    return topics


def _ensure_sections(sections: List[str], title: str, summary_lines: List[str], desired: int = 5) -> List[str]:
    deduped = _deduplicate_sections(sections, title)
    if len(deduped) >= desired:
        return deduped
    generated = _generate_topics_from_summary(summary_lines, desired * 2)
    existing_norms = {_normalize_label(item) for item in deduped}
    for topic in generated:
        if len(deduped) >= desired:
            break
        norm_topic = _normalize_label(topic)
        if not norm_topic:
            continue
        if norm_topic == _normalize_label(title):
            continue
        if norm_topic in existing_norms:
            continue
        deduped.append(topic)
        existing_norms.add(norm_topic)

    while len(deduped) < desired:
        fallback_topic = f"Tema {len(deduped) + 1}"
        if _normalize_label(fallback_topic) in existing_norms:
            fallback_topic = f"Tema {len(deduped) + 1} extra"
        deduped.append(fallback_topic)
        existing_norms.add(_normalize_label(fallback_topic))
    return deduped


def _summarize_markdown(md_path: Path, title: str) -> tuple[List[str], List[str]]:
    global _SUMMARY_WARNING_EMITTED
    if _OPENAI_CLIENT is None:
        if not _SUMMARY_WARNING_EMITTED:
            print("⚠️ Cliente OpenAI no disponible; se usarán las primeras líneas como resumen.")
            _SUMMARY_WARNING_EMITTED = True
        return _fallback_summary_and_sections(md_path)

    raw_text = _load_markdown_text(md_path)
    if not raw_text:
        return ["[Contenido no disponible para resumen]"], ["(Secciones no disponibles)"]

    truncated = raw_text[:MAX_SUMMARY_INPUT_CHARS]
    lang_hint = _guess_language(truncated)
    system = (
        "Eres un asistente editorial. Identifica el idioma principal del texto (español o inglés) "
        "y resume el contenido usando exactamente ese idioma. "
        "No traduzcas el texto ni mezcles idiomas. "
        f"Tu resumen debe rondar las {SUMMARY_WORD_TARGET} palabras y conservar las ideas clave. "
        "Devuélvelo como uno o varios párrafos directos, sin encabezados, etiquetas ni prefijos como "
        "'Resumen:' o indicaciones de idioma."
    )
    prompt_lines = [
        "Genera un resumen atractivo seguido de una lista de apartados del artículo delimitado por <<<texto>>>.",
        "",
        "Requisitos:",
        "- summary: 250-300 palabras en el mismo idioma que el texto. Empieza con 1-2 frases de gancho claras y objetivas, sin opiniones propias.",
        "- Separa los párrafos del resumen con una línea en blanco.",
        "- sections: tras el resumen añade una línea en blanco y una lista de apartados, cada línea empezando por '- '.",
        "  - Usa encabezados reales (H1-H3) si existen; si faltan, inventa exactamente 5 temas breves que representen el contenido.",
        "  - No repitas el título original ni variantes cercanas en la lista.",
        "  - No mezcles niveles ni añadas numeración salvo que esté en el original.",
        "- No inventes hechos ni añadas etiquetas o prefijos como 'Resumen:' o 'Secciones:'.",
        "",
        f"El texto está mayoritariamente en {lang_hint}. Usa exclusivamente ese idioma.",
        "",
        "<<<",
        truncated,
        ">>>",
    ]
    prompt = "\n".join(prompt_lines)

    try:
        summary = _call_openai(system, prompt, max_tokens=SUMMARY_MAX_OUTPUT_TOKENS)
    except Exception as exc:
        print(f"⚠️ No se pudo generar resumen IA para {md_path.name}: {exc}")
        return _fallback_summary_and_sections(md_path)

    summary_text = summary.strip()
    if not summary_text:
        return _fallback_summary_and_sections(md_path)

    summary_lines, sections = _parse_summary_sections(summary_text)
    if not summary_lines:
        return _fallback_summary_and_sections(md_path)
    sections = _ensure_sections(sections, title, summary_lines)
    return summary_lines, sections


def _fallback_lines(md_path: Path, limit: int) -> List[str]:
    lines: List[str] = []
    try:
        with md_path.open("r", encoding="utf-8") as fh:
            for _, raw_line in zip(range(limit), fh):
                lines.append(raw_line.rstrip("\n"))
    except UnicodeDecodeError:
        return ["[Contenido no disponible: codificación inválida]"]
    if not lines:
        return ["[Contenido vacío]"]
    return lines


def _build_entry(md_path: Path) -> Iterable[str]:
    url = _read_url(md_path)
    title = _original_filename(url)
    if title == "(Sin título)":
        title = md_path.name
    year = _extract_year_from_url(url)
    if year is None:
        try:
            year = str(datetime.fromtimestamp(md_path.stat().st_mtime).year)
        except FileNotFoundError:
            year = str(datetime.now().year)
    display_url = url or "(URL no disponible)"
    summary_lines, sections = _summarize_markdown(md_path, title)

    yield f"# {title} - {year}"
    yield ""
    yield f"URL: {display_url}"
    yield ""
    yield from summary_lines
    yield ""
    for section in sections:
        yield f"- {section}"


def build_pulse_digest() -> Path | None:
    md_files = _list_markdown_files()
    if not md_files:
        print("⚠️ No hay ficheros Markdown en Pulse/Incoming.")
        return None

    PULSE_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    today_stamp = now.strftime("%Y%m%d")
    today_title = now.strftime("%d-%m-%Y")
    output_path = PULSE_DIR / f"pulse-{today_stamp}.md"

    lines: list[str] = [f"# Resumen Pulse {today_title}", ""]
    for index, md_path in enumerate(md_files):
        print(f"⏳ Resumiendo {md_path.name} ({index + 1}/{len(md_files)})...")
        lines.extend(_build_entry(md_path))
        if index < len(md_files) - 1:
            lines.extend(("", "---", ""))

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"📝 Resumen creado en: {output_path}")

    for md_path in md_files:
        try:
            md_path.unlink(missing_ok=True)  # type: ignore[arg-type]
        except TypeError:  # pragma: no cover - compat con Python <3.8
            if md_path.exists():
                md_path.unlink()
        url_path = md_path.with_suffix(".url")
        if url_path.exists():
            url_path.unlink()

    return output_path


def main() -> None:
    build_pulse_digest()


if __name__ == "__main__":
    main()
