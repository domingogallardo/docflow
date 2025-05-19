import os
import re
import shutil

# Lista de meses en inglés
months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

# Compilar la expresión regular para buscar fechas en el formato "Month day, year"
def compile_regex_for_year(year):
    month_regex = '|'.join(months)
    return re.compile(rf'\b({month_regex}) \d{{1,2}},\s*{year}\b')

# Función para buscar en archivos
def search_dates_in_files(years, directory='.'):
    regexes = {year: compile_regex_for_year(year) for year in years}
    matching_lines = []
    matching_files = {year: set() for year in years}

    for file in os.listdir(directory):
        file_path = os.path.join(directory, file)
        if os.path.isfile(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line_num, line in enumerate(f, start=1):
                        for year, regex in regexes.items():
                            if regex.search(line) and len(line) < 80:
                                matching_lines.append((file_path, line_num, line.strip()))
                                matching_files[year].add(file_path)
            except (UnicodeDecodeError, IOError):
                # Ignorar archivos que no se pueden leer como texto
                continue

    return matching_lines, matching_files

# Años a buscar
years = list(range(2000, 2025))

# Buscar fechas en los archivos del directorio actual
results, files_to_move = search_dates_in_files(years)

# Mostrar los resultados y mover archivos
if results:
    print(f"\nEncontrado(s) {len(results)} resultado(s):")
    for file_path, line_num, line in results:
        print(f"Archivo: {file_path}, Línea: {line_num}, Texto: {line}")

    # Mover archivos encontrados al directorio de destino correspondiente
    for year, file_paths in files_to_move.items():
        destination_directory = os.path.join('..', str(year))
        for file_path in file_paths:
            destination_path = os.path.join(destination_directory, os.path.basename(file_path))
            shutil.move(file_path, destination_path)
            print(f"Archivo movido a {destination_path}")
else:
    print(f"\nNo se encontraron fechas.")
