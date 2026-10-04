"""Consume the append-only iCloud Shortcuts queue without losing failed captures."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import config as cfg
import utils as U
from web_clipper_wrapper import download_url_to_markdown, read_urls_from_file

DEFAULT_QUEUE = Path.home() / "Library/Mobile Documents/iCloud~is~workflow~my~workflows/Documents/Docflow/queue.md"


@dataclass(frozen=True)
class Capture:
    id: str
    url: str
    note: str
    added: str
    metadata: dict


def valid_url(value: str) -> str:
    parts = urlsplit(value.strip())
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password or any(c.isspace() for c in value.strip()):
        raise ValueError("Capture must contain an HTTP(S) URL without embedded credentials")
    return value.strip()


def parse_queue(text: str) -> tuple[list[Capture], list[str]]:
    captures, errors = [], []
    for block in re.split(r"(?m)^### Capture\s*$", text)[1:]:
        fields = dict(re.findall(r"(?m)^- ([A-Za-z0-9-]+): *(.*)$", block))
        try:
            raw = base64.b64decode(fields["Input-Base64"].strip(), validate=True).decode("utf-8")
            note = base64.b64decode(fields.get("Note-Base64", "").strip(), validate=True).decode("utf-8")
            metadata = {}
            if raw.lstrip().startswith("{"):
                metadata = json.loads(raw)
                if not isinstance(metadata, dict):
                    raise ValueError("Unread input must be a dictionary")
                url = valid_url(metadata.get("url", ""))
            else:
                url_input = raw
                if fields.get("URLs-Base64"):
                    url_input = base64.b64decode(fields["URLs-Base64"].strip(), validate=True).decode("utf-8")
                matches = re.findall(r'https?://[^\s<>"\uFFFC]+', url_input)
                if len(matches) != 1:
                    raise ValueError("Share exactly one article URL at a time")
                url = valid_url(matches[0])
            added = fields.get("Added", "")
            identity = json.dumps([raw, note, added], ensure_ascii=False).encode()
            captures.append(Capture(hashlib.sha256(identity).hexdigest(), url, note, added, metadata))
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            errors.append(str(exc))
    return captures, errors


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def document_index(base_dir: Path) -> tuple[dict[str, Path], dict[str, Path]]:
    by_url, by_id = {}, {}
    for root in (base_dir / "Incoming", base_dir / "Posts"):
        if not root.exists():
            continue
        for path in root.rglob("*.md"):
            meta, _ = U.split_front_matter(path.read_text(encoding="utf-8", errors="replace"))
            if not meta:
                continue
            for key in ("docflow-source-url", "source_url", "docflow-final-url", "docflow-original-url"):
                if meta.get(key):
                    by_url[meta[key]] = path
            if meta.get("docflow-capture-id"):
                by_id[meta["docflow-capture-id"]] = path
    return by_url, by_id


def completed_document(path: Path, base_dir: Path) -> bool:
    html = path.with_suffix(".html")
    return (path.is_file() and path.stat().st_size > 0 and (base_dir / "Posts") in path.parents
            and html.is_file() and html.stat().st_size > 0)


def process_queue(queue: Path, base_dir: Path, *, dry_run: bool = False, downloader=None, ingest=None) -> dict:
    """Download, persist receipts, ingest, and confirm each resulting Markdown/HTML pair."""
    captures, errors = parse_queue(queue.read_text(encoding="utf-8") if queue.exists() else "")
    state_path = base_dir / "state/capture_queue.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"captures": {}}
    receipts = state["captures"]
    pending = [c for c in captures if not (
        receipts.get(c.id, {}).get("status") == "completed"
        and completed_document(Path(receipts[c.id]["document"]), base_dir)
    )]
    report = {"entries": len(captures), "pending": len(pending), "completed": 0, "failed": 0, "parse_errors": errors}
    if dry_run or not pending:
        return report
    downloader = downloader or download_url_to_markdown
    by_url, by_id = document_index(base_dir)
    paths = {}
    for capture in pending:
        receipt = receipts.setdefault(capture.id, {**asdict(capture), "status": "pending"})
        try:
            path = by_id.get(capture.id) or by_url.get(capture.url)
            if path is None:
                result = downloader(capture.url, output_dir=base_dir / "Incoming")
                path = result.output_path
                if not path.is_file() or not path.read_text(encoding="utf-8").strip():
                    raise ValueError("Downloader did not produce a nonempty Markdown file")
                meta, body = U.split_front_matter(path.read_text(encoding="utf-8"))
                if not body.strip() or not any(meta.get(k) for k in ("docflow-source-url", "source_url", "docflow-final-url")):
                    raise ValueError("Downloaded Markdown is missing its body or source metadata")
                path.write_text(U.upsert_front_matter(path.read_text(encoding="utf-8"), {
                    "docflow-capture-id": capture.id,
                    "docflow-capture-note": capture.note,
                    "docflow-capture-added": capture.added,
                    "docflow-capture-origin": "Unread" if capture.metadata else "Share Sheet",
                }), encoding="utf-8")
                by_url[capture.url] = path
                by_id[capture.id] = path
            paths[capture.id] = path
            receipt.update(status="downloaded", document=str(path), error="")
        except Exception as exc:
            receipt.update(status="pending", error=str(exc))
            report["failed"] += 1
            print(f"Capture download failed: {exc}")
        atomic_json(state_path, state)

    if any(not completed_document(path, base_dir) for path in paths.values()):
        try:
            if ingest:
                ingest()
            else:
                subprocess.run(["/bin/bash", str(Path(__file__).parent / "bin/docflow.sh"), "md"], check=True)
        except Exception as exc:
            for identity in paths:
                receipts[identity]["error"] = f"Ingestion did not complete: {exc}"
            atomic_json(state_path, state)
    by_url, by_id = document_index(base_dir)
    for identity, previous_path in paths.items():
        receipt = receipts[identity]
        path = by_id.get(identity) or by_url.get(receipt["url"]) or previous_path
        if completed_document(path, base_dir):
            receipt.update(status="completed", document=str(path), completed_at=datetime.now(timezone.utc).isoformat(), error="")
            report["completed"] += 1
        else:
            receipt.update(status="downloaded", error=receipt.get("error") or "Markdown/HTML pair is not archived yet")
            report["failed"] += 1
    atomic_json(state_path, state)
    completed_urls = [receipts[identity]["url"] for identity in paths if receipts[identity]["status"] == "completed"]
    history = base_dir / "Incoming/processed_history.txt"
    existing_history = set(read_urls_from_file(history))
    new_history = list(dict.fromkeys(url for url in completed_urls if url not in existing_history))
    if new_history:
        from pipeline_manager import DocumentProcessor
        DocumentProcessor._append_url_history(new_history, history_path=history)
    # Separate status output: never rewrite the iPhone's append-only input file.
    lines = ["# Docflow captures", "", "The capture queue is append-only. This file shows processing status.", ""]
    for receipt in receipts.values():
        marker = "x" if receipt["status"] == "completed" else " "
        lines.append(f"- [{marker}] {receipt['url']}")
        if receipt.get("note"):
            lines.append("  Note: " + receipt["note"].replace("\n", " "))
        if receipt.get("error"):
            lines.append("  Error: " + receipt["error"].replace("\n", " "))
    for error in errors:
        lines.append("- Parse error: " + error.replace("\n", " "))
    queue.with_name("status.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    report = process_queue(args.queue, cfg.BASE_DIR, dry_run=args.dry_run)
    print(json.dumps(report, ensure_ascii=False))
    return int(bool(report["failed"] or report["parse_errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
