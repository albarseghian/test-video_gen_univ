import os
import shutil

def filter_and_copy_wav_files():
    source_folder = os.path.join("tests", "voices")
    destination_folder = "new_filtered_format"

    # Create the destination folder if it doesn't exist
    if not os.path.exists(destination_folder):
        os.makedirs(destination_folder)
        print(f"Created directory: {destination_folder}")

    # List files in the source folder
    try:
        files = os.listdir(source_folder)
    except FileNotFoundError:
        print(f"Error: Source folder '{source_folder}' not found.")
        return

    wav_count = 0
    for filename in files:
        if filename.lower().endswith(".wav"):
            source_path = os.path.join(source_folder, filename)
            destination_path = os.path.join(destination_folder, filename)
            
            # Copy the file
            shutil.copy2(source_path, destination_path)
            print(f"Copied: {filename}")
            wav_count += 1

    print(f"\nFinished! Copied {wav_count} .wav files to '{destination_folder}'.")

if __name__ == "__main__":
    filter_and_copy_wav_files()
