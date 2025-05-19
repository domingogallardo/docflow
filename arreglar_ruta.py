import fileinput
import re
from pathlib import Path

HISTORIAL = Path("/Users/domingo/⭐️ Documentación/Historial.txt")

# Expresiones de sustitución
pat_md  = re.compile(r'^\./Incoming/(.+\.md)$')
pat_pdf = re.compile(r'^\./Incoming/(.+\.pdf)$')

with fileinput.FileInput(HISTORIAL, inplace=True, backup=".bak", encoding="utf-8") as f:
    for line in f:
        if pat_md.match(line):
            line = pat_md.sub(r'./Posts/Posts 2025/\1', line)
        elif pat_pdf.match(line):
            line = pat_pdf.sub(r'./Pdfs/Pdfs 2025/\1', line)
        print(line, end="")

print("Reemplazo completado.")