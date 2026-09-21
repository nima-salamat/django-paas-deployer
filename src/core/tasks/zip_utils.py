from celery import shared_task
import zipfile
import os

@shared_task
def unzip_files(file_path):
    if not os.path.exists(file_path):
        print(f"[UNZIP] File not found: {file_path}")
        return

    base_path = os.path.dirname(file_path)
    zip_name = os.path.splitext(os.path.basename(file_path))[0]
    extract_to = os.path.join(base_path, zip_name) # now its in a same folder where zip was but inside extra folder named after the zip_name

    try:
        os.makedirs(extract_to, exist_ok=True)
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        print(f"[UNZIP] Successfully extracted to: {extract_to}")
    except zipfile.BadZipFile:
        print(f"[UNZIP] Invalid ZIP file: {file_path}")
    except Exception as e:
        print(f"[UNZIP] Error while extracting: {e}")
