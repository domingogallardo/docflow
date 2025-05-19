#!/bin/bash
set -e

#############################################################################
# RUTAS BASE
#############################################################################
BASE="/Users/domingo/⭐️ Documentación"
INCOMING="$BASE/Incoming"

POSTS_DEST="$BASE/Posts/Posts 2025"
PDFS_DEST="$BASE/Pdfs/Pdfs 2025"          # ← NUEVO destino para los PDF
HISTORIAL="$BASE/Historial.txt"
#############################################################################

echo "Ejecutando scrape.py..."
python scrape.py
echo "Ejecutando convertir_html_md.py..."
python convertir_html_md.py
echo "Ejecutando fix_html_encoding.py..."
python fix_html_encoding.py
echo "Ejecutando ajustar_ancho_imagenes.py"
python ajustar_ancho_imagenes.py
echo "Ejecutando add_margen_html.py..."
python add_margen_html.py

echo "Eliminando procesados.txt anterior (si existe)..."
rm -f procesados.txt

echo "Ejecutando actualizar_titulo.py..."
python actualizar_titulo.py

#############################################################################
# CREAR carpetas destino si no existen
#############################################################################
mkdir -p "$POSTS_DEST" "$PDFS_DEST"

#############################################################################
# MOVER POSTS procesados (html/htm/md)
#############################################################################
echo "Moviendo POSTS a ${POSTS_DEST}..."
mv "$INCOMING"/*.{html,htm,md} "$POSTS_DEST/" 2>/dev/null || true

#############################################################################
# MOVER PDFs procesados
#############################################################################
echo "Moviendo PDFs a ${PDFS_DEST}..."
mv "$INCOMING"/*.pdf "$PDFS_DEST/" 2>/dev/null || true

#############################################################################
# ACTUALIZAR Historial
#############################################################################
echo "Actualizando Historial..."
cat procesados.txt "$HISTORIAL" > "$HISTORIAL.tmp" && mv "$HISTORIAL.tmp" "$HISTORIAL"

echo "Arreglando rutas..."
python arreglar_ruta.py

echo "Proceso completado."