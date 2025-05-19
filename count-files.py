import os

def count_files_in_directory(directory_path):
    files_count = 0
    for path in os.listdir(directory_path):
        if os.path.isfile(os.path.join(directory_path, path)):
            files_count += 1
    return files_count

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) != 2:
        print("Usage: python script.py /path/to/directory")
        sys.exit(1)

    directory_path = sys.argv[1]
    count = count_files_in_directory(directory_path)
    print(f'There are {count} files in the directory.')
