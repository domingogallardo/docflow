#!/usr/bin/env python3
"""
PDFProcessor - standalone module for PDF processing.
"""
from datetime import datetime
from pathlib import Path
import shutil
from typing import Iterable, List

import utils as U
from path_utils import unique_path


class PDFProcessor:
    """Specialized processor for PDF files."""
    
    def __init__(
        self,
        incoming_dir: Path,
        destination_dir: Path,
        *,
        source_dirs: Iterable[Path] = (),
    ):
        self.incoming_dir = incoming_dir
        self.destination_dir = destination_dir
        self.source_dirs = [Path(path).expanduser() for path in source_dirs]
    
    def process_pdfs(self) -> List[Path]:
        """Process PDFs by moving them directly to their destination (no pipeline)."""
        print("📚 Processing PDFs...")
        self._import_source_pdfs()
        
        # PDFs do not need processing, only moving.
        pdfs = U.list_files({".pdf"}, root=self.incoming_dir)
        
        if not pdfs:
            print("📚 No PDFs found to process")
            return []
        
        moved_pdfs = U.move_files(pdfs, self.destination_dir)
        
        if moved_pdfs:
            print(f"📚 {len(moved_pdfs)} PDF(s) moved to {self.destination_dir}")

        return moved_pdfs

    def _import_source_pdfs(self) -> List[Path]:
        """Move PDFs from configured external folders into Incoming/."""
        imported: List[Path] = []
        self.incoming_dir.mkdir(parents=True, exist_ok=True)

        for source_dir in self.source_dirs:
            if not source_dir.is_dir():
                self._write_import_audit(f"source missing or not a directory: {source_dir}")
                continue
            try:
                same_dir = source_dir.resolve() == self.incoming_dir.resolve()
            except OSError:
                same_dir = False
            if same_dir:
                self._write_import_audit(f"source skipped because it is Incoming: {source_dir}")
                continue

            pdf_candidates = sorted(source_dir.glob("*.pdf"))
            placeholder_candidates = sorted(
                path
                for path in source_dir.glob("*.icloud")
                if ".pdf" in path.name.lower()
            )
            has_activity = bool(pdf_candidates or placeholder_candidates)
            audit_events = [
                f"scanning {source_dir}: "
                f"{len(pdf_candidates)} PDF candidate(s), "
                f"{len(placeholder_candidates)} iCloud placeholder candidate(s)"
            ]
            for placeholder_path in placeholder_candidates:
                audit_events.append(f"placeholder not importable yet: {placeholder_path.name}")

            imported_from_source = 0
            ignored_from_source = 0
            for source_path in pdf_candidates:
                if not source_path.is_file():
                    ignored_from_source += 1
                    audit_events.append(f"ignored non-file PDF candidate: {source_path.name}")
                    continue

                destination = unique_path(self.incoming_dir / source_path.name)
                try:
                    shutil.move(str(source_path), destination)
                except Exception as exc:
                    message = f"error importing PDF from {source_path}: {exc}"
                    print(f"❌ Error importing PDF from {source_path}: {exc}")
                    audit_events.append(message)
                    continue

                imported.append(destination)
                imported_from_source += 1
                print(f"📥 Imported PDF from iCloud Downloads: {destination.name}")
                audit_events.append(f"imported PDF: {source_path.name} -> {destination}")

            if has_activity:
                audit_events.append(
                    f"finished {source_dir}: imported {imported_from_source}, ignored {ignored_from_source}"
                )
                for event in audit_events:
                    self._write_import_audit(event)

        return imported

    def _write_import_audit(self, message: str) -> None:
        """Append an import audit entry and mirror it to stdout for cron logs."""
        timestamp = datetime.now().isoformat(timespec="seconds")
        line = f"{timestamp} pdf {message}"
        print(f"🧾 PDF import audit: {message}")
        try:
            audit_path = self.incoming_dir / "import_audit.log"
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            with audit_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception as exc:
            print(f"⚠️ Could not write PDF import audit: {exc}")
