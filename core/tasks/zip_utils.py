from celery import shared_task


@shared_task
def unzip_files(file_path):
    # unzip the files
    print(f"Unzipping: {file_path}")