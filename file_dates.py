import os
import re

# Lista de meses en inglés
months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

# Compilar la expresión regular para buscar fechas en el formato "Month day, year"
def compile_regex_for_year(year):
    month_regex = '|'.join(months)
    return re.compile(rf'\b({month_regex}) \d{{1,2}},\s*{year}\b')

# Función para buscar en archivos
def search_dates_in_files(year, directory='.'):
    regex = compile_regex_for_year(year)
    matching_lines = []

    for file in os.listdir(directory):
        file_path = os.path.join(directory, file)
        if os.path.isfile(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line_num, line in enumerate(f, start=1):
                        if regex.search(line) and len(line) < 80:
                            matching_lines.append((file_path, line_num, line.strip()))
            except (UnicodeDecodeError, IOError):
                # Ignorar archivos que no se pueden leer como texto
                continue

    return matching_lines

# Solicitar el año al usuario
year = input("Ingrese el año que desea buscar: ")

# Buscar fechas en los archivos del directorio actual
results = search_dates_in_files(year)

# Mostrar los resultados
if results:
    print(f"\nEncontrado(s) {len(results)} resultado(s) para el año {year}:")
    for file_path, line_num, line in results:
        print(f"Archivo: {file_path}, Línea: {line_num}, Texto: {line}")
else:
    print(f"\nNo se encontraron fechas para el año {year}.")
