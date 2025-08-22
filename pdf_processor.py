#!/usr/bin/env python3
"""
PDFProcessor - Módulo independiente para el procesamiento de archivos PDF
"""
from pathlib import Path
from typing import List

import utils as U


class PDFProcessor:
    """Procesador especializado para archivos PDF."""
    
    def __init__(self, incoming_dir: Path, destination_dir: Path):
        self.incoming_dir = incoming_dir
        self.destination_dir = destination_dir
    
    def process_pdfs(self) -> List[Path]:
        """Procesa PDFs moviéndolos directamente a su destino (sin pipeline)."""
        print("📚 Procesando PDFs...")
        
        # Los PDFs no necesitan procesamiento, solo moverlos
        pdfs = U.list_files({".pdf"}, root=self.incoming_dir)
        
        if not pdfs:
            print("📚 No se encontraron PDFs para procesar")
            return []
        
        moved_pdfs = U.move_files(pdfs, self.destination_dir)
        
        if moved_pdfs:
            print(f"📚 {len(moved_pdfs)} PDF(s) movidos a {self.destination_dir}")

        return moved_pdfs
