from celery import shared_task

@shared_task
def unzip_files(file_path):
    # unzip the files
    print(f"Unzipping: {file_path}")

@shared_task
def handle_deploy_start(deploy_id):
    print(f"[START] Deploy {deploy_id} is starting.")
    # start the server/container

@shared_task
def handle_deploy_stop(deploy_id):
    print(f"[STOP] Deploy {deploy_id} is stopping.")
    # stop the server/container
