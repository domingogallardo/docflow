#!/usr/bin/env python3
"""
Convert Markdown files to HTML in the Incoming/ directory.
Applies the same processing as podcasts: conversion + margins.
"""
from pathlib import Path
import config as cfg
import utils as U


def convert_md_to_html():
    """Convert all .md files in Incoming/ to HTML."""
    incoming_dir = Path(cfg.INCOMING)
    md_files = list(incoming_dir.glob("*.md"))
    
    if not md_files:
        print("📝 No se encontraron archivos .md para convertir")
        return
    
    print(f"📝 Convirtiendo {len(md_files)} archivo(s) Markdown a HTML...")
    
    for md_file in md_files:
        html_path = md_file.with_suffix(".html")
        
        # Skip if the HTML already exists.
        if html_path.exists():
            print(f"⏭️  Saltando {md_file.name} (HTML ya existe)")
            continue
        
        try:
            # Read Markdown content.
            md_text = md_file.read_text(encoding="utf-8", errors="replace")
            
            # Convert to HTML using the centralized function.
            full_html = U.markdown_to_html(md_text, title=md_file.stem)
            
            # Save HTML.
            html_path.write_text(full_html, encoding="utf-8")
            print(f"✅ HTML generado: {html_path.name}")
            
        except Exception as e:
            print(f"❌ Error convirtiendo {md_file.name}: {e}")
            import traceback
            traceback.print_exc()
    
    # Apply margins to all generated HTML.
    print("📏 Aplicando márgenes...")
    U.add_margins_to_html_files(incoming_dir)


if __name__ == "__main__":
    convert_md_to_html() 
