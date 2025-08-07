import os
import io
import tarfile
import zipfile

def convert_zip_to_tar(zip_path: str) -> io.BytesIO:
    """
    Converts a ZIP file at zip_path into an in-memory TAR stream.
    Returns: tar_stream (io.BytesIO)
    """
    if not os.path.exists(zip_path):
        raise FileNotFoundError(f"ZIP file not found at: {zip_path}")
    
    tar_stream = io.BytesIO()
    
    with tarfile.open(fileobj=tar_stream, mode='w') as tar:
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            for zip_info in zipf.infolist():
                file_data = zipf.read(zip_info.filename)
                tar_info = tarfile.TarInfo(name=zip_info.filename)
                tar_info.size = len(file_data)
                tar.addfile(tar_info, io.BytesIO(file_data))
    
    tar_stream.seek(0)
    return tar_stream

def merge_tar_streams(*streams: io.BytesIO) -> io.BytesIO:
    """
    Merge multiple tar streams into a single tar stream.
    """
    combined = io.BytesIO()
    with tarfile.open(fileobj=combined, mode='w') as tar_out:
        for stream in streams:
            stream.seek(0)
            with tarfile.open(fileobj=stream, mode='r') as tar_in:
                for member in tar_in.getmembers():
                    file_data = tar_in.extractfile(member)
                    if file_data is not None:
                        tar_out.addfile(member, file_data)
                    else:
                        tar_out.addfile(member)
    combined.seek(0)
    return combined


def create_dockerfile_tar(dockerfile_text: str) -> io.BytesIO:
    """
    Creates an in-memory TAR stream containing only the Dockerfile.
    Returns: tar_stream (io.BytesIO)
    """
    dockerfile_bytes = dockerfile_text.encode('utf-8')
    tar_stream = io.BytesIO()
    
    with tarfile.open(fileobj=tar_stream, mode='w') as tar:
        dockerfile_info = tarfile.TarInfo(name="Dockerfile")
        dockerfile_info.size = len(dockerfile_bytes)
        tar.addfile(dockerfile_info, io.BytesIO(dockerfile_bytes))
    
    tar_stream.seek(0)
    return tar_stream
