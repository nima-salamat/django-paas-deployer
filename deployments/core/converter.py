import os
import io
import tarfile
import zipfile




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
    return merge_tar_streams(tar_stream)


