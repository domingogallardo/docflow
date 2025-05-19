import os
import sys

def rename_files_in_directory(directory_path):
    # Get a list of files in the directory
    files = os.listdir(directory_path)

    for file_name in files:
        # Check if the file name starts with a number followed by a space
        if file_name[0].isdigit() and ' ' in file_name:
            # Split the file name to remove the number and the space
            new_name = file_name.split(' ', 1)[1]
            original_new_name = new_name
            counter = 1

            # Ensure the new name doesn't conflict with an existing file
            while os.path.exists(os.path.join(directory_path, new_name)):
                name, ext = os.path.splitext(original_new_name)
                new_name = f"{name}_{counter}{ext}"
                counter += 1

            # Rename the file
            old_path = os.path.join(directory_path, file_name)
            new_path = os.path.join(directory_path, new_name)
            os.rename(old_path, new_path)
            print(f"Renamed: '{file_name}' to '{new_name}'")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python script.py /path/to/directory")
        sys.exit(1)

    directory_path = sys.argv[1]
    rename_files_in_directory(directory_path)
