#!/usr/bin/env python3
"""
PDFProcessor - standalone module for PDF processing.
"""
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
                continue
            try:
                same_dir = source_dir.resolve() == self.incoming_dir.resolve()
            except OSError:
                same_dir = False
            if same_dir:
                continue

            for source_path in sorted(source_dir.glob("*.pdf")):
                if not source_path.is_file():
                    continue

                destination = unique_path(self.incoming_dir / source_path.name)
                try:
                    shutil.move(str(source_path), destination)
                except Exception as exc:
                    print(f"❌ Error importing PDF from {source_path}: {exc}")
                    continue

                imported.append(destination)
                print(f"📥 Imported PDF from iCloud Downloads: {destination.name}")

        return imported
