#!/usr/bin/env python3
"""PDFProcessor - standalone module for PDF processing."""
from pathlib import Path
from typing import List

import utils as U


class PDFProcessor:
    """Specialized processor for PDF files."""
    
    def __init__(
        self,
        incoming_dir: Path,
        destination_dir: Path,
    ):
        self.incoming_dir = incoming_dir
        self.destination_dir = destination_dir
    
    def process_pdfs(self) -> List[Path]:
        """Process PDFs by moving them directly to their destination (no pipeline)."""
        print("📚 Processing PDFs...")

        # PDFs do not need processing, only moving.
        pdfs = U.list_files({".pdf"}, root=self.incoming_dir)
        
        if not pdfs:
            print("📚 No PDFs found to process")
            return []
        
        moved_pdfs = U.move_files(pdfs, self.destination_dir)
        for pdf_path in moved_pdfs:
            U.ensure_pdf_sidecar_markdown(pdf_path, base_dir=self.destination_dir.parent)
        
        if moved_pdfs:
            print(f"📚 {len(moved_pdfs)} PDF(s) moved to {self.destination_dir}")

        return moved_pdfs
