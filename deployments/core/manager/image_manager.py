import docker.errors
from .client_manager import Client
import logging
import tarfile
import tempfile
import zipfile
import os
import json
import traceback
import io
import docker
from docker.errors import BuildError, ImageNotFound

logger = logging.getLogger(__name__)

def safe_extract(tar: tarfile.TarFile, path: str, max_bytes: int = 500 * 1024 * 1024):
    """
    Extract tar safely into `path`.
    - prevents path traversal
    - rejects symlinks and hard links
    - limits total extracted bytes to max_bytes
    """
    abs_base = os.path.abspath(path)
    total_written = 0

    for member in tar.getmembers():
        # Reject symbolic/hard links
        if member.islnk() or member.issym():
            raise Exception(f"Tar contains links which aren't allowed: {member.name}")

        # Compute destination path
        member_path = os.path.join(path, member.name)
        abs_target = os.path.abspath(member_path)

        # Prevent path traversal
        if not abs_target.startswith(abs_base + os.sep) and abs_target != abs_base:
            raise Exception(f"Unsafe tar path detected: {member.name}")

        # Directory
        if member.isdir():
            os.makedirs(abs_target, exist_ok=True)
            # Preserve permissions where appropriate
            try:
                os.chmod(abs_target, member.mode)
            except Exception:
                pass
            continue

        # If it's not a regular file (e.g. device), skip/raise
        if not member.isreg():
            # ignore special files but you may want to raise instead
            raise Exception(f"Unsupported tar entry (not a regular file): {member.name}")

        # Ensure parent dir exists
        parent = os.path.dirname(abs_target)
        if os.path.exists(parent) and not os.path.isdir(parent):
            os.remove(parent)
        os.makedirs(parent, exist_ok=True)


        # Extract file content via extractfile to avoid using extractall
        f = tar.extractfile(member)
        if f is None:
            # empty file entry
            open(abs_target, "wb").close()
            continue

        # Write file chunked, checking total size
        with open(abs_target, "wb") as out_f:
            while True:
                chunk = f.read(64 * 1024)
                if not chunk:
                    break
                out_f.write(chunk)
                total_written += len(chunk)
                if total_written > max_bytes:
                    raise Exception("Extracted data exceeds allowed limit")

        # try to set file mode (best-effort)
        try:
            os.chmod(abs_target, member.mode)
        except Exception:
            pass


class Image(Client):
    def __init__(
        self,
        name: str,
        tag: str = "latest",
        dockerfile_text: str = None,
        tarfile: io.BytesIO = None
    ):
        super().__init__()
        self.name = name
        self.tag = tag
        self.dockerfile_text = dockerfile_text
        self.tarfile = tarfile
        self.image_ref = f"{self.name}:{self.tag}" if tag else self.name

        
        
    def _iter_build_stream(self, stream):
        """
        Normalize build stream chunks to dicts.
        Accepts both bytes and dict chunks and yields dicts.
        """
        for chunk in stream:
            # If chunk is bytes, try to decode then parse JSON
            if isinstance(chunk, (bytes, bytearray)):
                try:
                    text = chunk.decode("utf-8", "replace")
                    # Some streams are newline separated JSON objects
                    for line in text.splitlines():
                        if not line.strip():
                            continue
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            # fallback: yield as raw text under 'stream'
                            yield {"stream": line}
                except Exception:
                    # If decode fails for some reason, yield raw repr
                    yield {"stream": repr(chunk)}
            elif isinstance(chunk, dict):
                # already a dict (best case)
                yield chunk
            else:
                # unknown type -> stringify
                try:
                    yield {"stream": str(chunk)}
                except Exception:
                    yield {"stream": repr(chunk)}
    

    def _handle_build_stream(self, response, on_build_output=None):
        """
        Normalize build stream and:
         - log locally
         - call on_build_output(chunk) for each chunk if provided
        """
        for chunk in self._iter_build_stream(response):
            # first, give caller the raw chunk if they want it
            if on_build_output:
                try:
                    on_build_output(chunk)
                except Exception:
                    logger.exception("on_build_output callback failed")

            # then default logging behavior
            if 'stream' in chunk:
                logger.info(chunk['stream'].strip())
            elif 'status' in chunk:
                status = chunk.get('status')
                progress = chunk.get('progress')
                if progress:
                    logger.info(f"{status} {progress}")
                else:
                    logger.info(status)
            elif 'error' in chunk:
                logger.error(chunk.get('error'))
                # propagate error to caller
                raise BuildError(chunk.get('error'), build_log=[chunk])
            else:
                logger.debug(f"Build chunk: {chunk}")

    def create(self, on_build_output=None):
        """
        Build image. If on_build_output provided, it will be called for
        each build chunk (dict) as they arrive (good for streaming to UI).
        Returns the built image object.
        """
        if not self.dockerfile_text or not self.tarfile:
            raise ValueError("dockerfile_text and tarfile are required")
        

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                
                if isinstance(self.tarfile, (bytes, bytearray)):
                    tar_stream = io.BytesIO(self.tarfile)
                else:
                    tar_stream = self.tarfile
                # extract TAR from memory (safe)
                self.tarfile.seek(0)
                with tarfile.open(fileobj=tar_stream, mode="r:*") as tar:
                    safe_extract(tar, tmpdir, max_bytes=500*1024*1024)

                # If Dockerfile lives inside app/, build from that path:
                # (adjust if the user's archive layout differs)
                build_path = tmpdir
                # If app/ exists and Dockerfile inside app/, use that
                app_dir = os.path.join(tmpdir, "app")
                if os.path.isdir(app_dir) and os.path.exists(os.path.join(app_dir, "Dockerfile")):
                    build_path = app_dir
                else:
                    # otherwise write Dockerfile to root if needed
                    with open(os.path.join(tmpdir, "Dockerfile"), "w") as f:
                        f.write(self.dockerfile_text)

                # run build
                response = self.client.api.build(
                    path=build_path,
                    tag=f"{self.name}:{self.tag}",
                    rm=True,
                    decode=True
                )

                # stream & handle build output (real-time-ish)
                self._handle_build_stream(response, on_build_output=on_build_output)

                # return built image object
                return self.client.images.get(f"{self.name}:{self.tag}")

        except BuildError:
            # build errors already logged in _handle_build_stream
            raise
        except Exception:
            logger.error("Unexpected error while building Docker image")
            logger.error(traceback.format_exc())
            raise

    # ---------- image-inspection helpers ----------
    def inspect(self):
        """Return docker inspect dict for this image (raises if missing)."""
        image_ref = f"{self.name}:{self.tag}"
        image = self.client.images.get(image_ref)
        return image.attrs

    def history(self):
        """Return image history (list of layers / commands)."""
        image_ref = f"{self.name}:{self.tag}"
        return self.client.api.history(image_ref)

    def size(self):
        """Return image size in bytes.""" 
        attrs = self.inspect()
        # Inspect result usually has 'Size'
        return attrs.get("Size", 0)

    def labels(self):
        """Return image labels dict (or {})."""
        attrs = self.inspect()
        return attrs.get("Config", {}).get("Labels", {}) or {}

    def save_to_path(self, path: str):
        """
        Save image as a tar archive to given filesystem path.
        This writes incrementally (doesn't load all in memory).
        """
        image_ref = f"{self.name}:{self.tag}"
        image = self.client.images.get(image_ref)
        stream = image.save(named=True)  # generator of bytes
        with open(path, "wb") as f:
            for chunk in stream:
                f.write(chunk)
        return path

    def save_to_fileobj(self, fileobj):
        """
        Write image tar to a file-like object (must be opened for binary write).
        """
        image_ref = f"{self.name}:{self.tag}"
        image = self.client.images.get(image_ref)
        stream = image.save(named=True)
        for chunk in stream:
            fileobj.write(chunk)
        fileobj.flush()
        return fileobj

    @classmethod
    def remove_by_name(cls, name):
        """
        Remove image by name (name can include tag, e.g. 'repo:tag' or be image id).
        Returns True if removed, False if not found.
        Raises on unexpected errors.
        """
        client = Client()()
        try:
            image = client.images.get(name)
        except ImageNotFound:
            logger.info(f"Image '{name}' not found (nothing to remove)")
            return False
        except Exception as e:
            logger.error(f"Error while fetching image '{name}': {e}")
            raise

        try:
            # Use client.images.remove which accepts name or id
            # not forcing by default; change force=True if you want forced removal
            client.images.remove(image.id)
            logger.info(f"Image '{name}' removed successfully (id={image.id})")
            return True
        except Exception as e:
            logger.error(f"Failed to remove image '{name}' (id={getattr(image, 'id', None)}): {e}")
            raise

    @classmethod
    def check_exists(cls, name):
        """
        Check whether an image exists (name may include tag).
        Returns True if exists, False otherwise.
        """
        client = Client()()

        try:
            client.images.get(name)
            return True
        except ImageNotFound:
            return False
        except Exception as e:
            logger.error(f"Error while checking existence of image '{name}': {e}")
            raise


    
    def remove(self, force: bool = False) -> bool:
      
        try:
            try:
                image = self.client.images.get(self.image_ref)
            except ImageNotFound:
                logger.debug(f"Image '{self.image_ref}' not found (nothing to remove)")
                return True  
            
            image_id_short = image.id[:12] if hasattr(image, 'id') else 'unknown'
            
            try:
                self.client.images.remove(self.image_ref, force=force)
                logger.info(f"Image '{self.image_ref}' (ID: {image_id_short}) removed successfully")
                return True
                
            except docker.errors.APIError as e:
                if "referenced in multiple repositories" in str(e):
                    logger.warning(f"Image '{self.image_ref}' has multiple tags ({image.tags})")
                    
                    if force:
                        self.client.images.remove(self.image_ref, force=True)
                        logger.info(f"Image '{self.image_ref}' force removed")
                        return True
                    else:
                        logger.info(f"Only removing tag '{self.image_ref}' from image")
                        self.client.images.remove(self.image_ref)
                        return True
                
                logger.error(f"Docker API error removing '{self.image_ref}': {e}")
                raise
            
        except Exception as e:
            logger.error(f"Unexpected error removing image '{self.image_ref}': {e}")
            return False
    
    def remove_all(self, 
                   force: bool = False, 
                   keep_latest: bool = False,
                   keep_tags= None) -> dict:
      
        stats = {
            'total_found': 0,
            'removed': 0,
            'skipped': 0,
            'failed': 0,
            'kept': []
        }
        
        try:
            try:
                images = self.client.images.list(name=self.name)
                
                if not images:
                    all_images = self.client.images.list()
                    images = [img for img in all_images 
                             if any(self.name in tag for tag in img.tags)]
                
                stats['total_found'] = len(images)
                
                if not images:
                    logger.info(f"No images found with name '{self.name}'")
                    return stats
                    
            except Exception as e:
                logger.error(f"Error listing images: {e}")
                return stats
            
            images_sorted = sorted(
                images,
                key=lambda x: x.attrs.get('Created', ''),
                reverse=True
            )
            
            keep_tags = keep_tags or []
            if keep_latest and images_sorted:
                latest_tags = images_sorted[0].tags
                keep_tags.extend(latest_tags)
            
            for i, image in enumerate(images_sorted):
                should_keep = False
                
                for tag in image.tags:
                    if tag in keep_tags:
                        should_keep = True
                        stats['kept'].append(tag)
                        break
                
                if should_keep:
                    stats['skipped'] += 1
                    logger.debug(f"Skipping image with tags: {image.tags}")
                    continue
                
                image_removed = self._remove_image_with_tags(image, force)
                
                if image_removed:
                    stats['removed'] += 1
                else:
                    stats['failed'] += 1
            
            logger.info(f"Remove all completed for '{self.name}': "
                       f"{stats['removed']} removed, "
                       f"{stats['skipped']} skipped, "
                       f"{stats['failed']} failed, "
                       f"{len(stats['kept'])} kept")
            
            return stats
            
        except Exception as e:
            logger.error(f"Error in remove_all for '{self.name}': {e}")
            return stats
    
    def _remove_image_with_tags(self, image, force: bool = False) -> bool:

        image_id = image.id[:12] if hasattr(image, 'id') else 'unknown'
        
        try:
            for tag in image.tags:
                try:
                    self.client.images.remove(tag, force=force)
                    logger.debug(f"Removed tag: {tag}")
                except docker.errors.APIError as e:
                    if "referenced in multiple repositories" in str(e):
                        self.client.images.remove(tag, force=True)
                        logger.debug(f"Force removed tag: {tag}")
                    else:
                        logger.warning(f"Could not remove tag '{tag}': {e}")
            
            try:
                self.client.images.remove(image.id, force=True)
                logger.debug(f"Removed image ID: {image_id}")
            except Exception as e:
                logger.debug(f"Image ID {image_id} might already be removed: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove image with ID {image_id}: {e}")
            return False
    
    def list_all(self):
       
        try:
            images = self.client.images.list(name=self.name)
            
            result = []
            for img in images:
                result.append({
                    'id': img.id[:12],
                    'tags': img.tags,
                    'created': img.attrs.get('Created', ''),
                    'size': img.attrs.get('Size', 0),
                    'virtual_size': img.attrs.get('VirtualSize', 0)
                })
            
            result.sort(key=lambda x: x['created'], reverse=True)
            
            return result
            
        except Exception as e:
            logger.error(f"Error listing images for '{self.name}': {e}")
            return []
    
    def exists(self) -> bool:
        try:
            if self.tag:
                self.client.images.get(f"{self.name}:{self.tag}")
            else:
                images = self.client.images.list(name=self.name)
                return len(images) > 0
            return True
        except ImageNotFound:
            return False
    
    def get_image_info(self):
        try:
            if not self.tag:
                return None
                
            image = self.client.images.get(f"{self.name}:{self.tag}")
            return {
                'id': image.id,
                'tags': image.tags,
                'created': image.attrs.get('Created', ''),
                'size': image.attrs.get('Size', 0),
                'virtual_size': image.attrs.get('VirtualSize', 0),
                'labels': image.attrs.get('Labels', {}),
                'architecture': image.attrs.get('Architecture', '')
            }
        except ImageNotFound:
            return None
    
    @classmethod
    def prune_dangling_images(cls):
        client = Client()()
        client.images.prune(filters={"dangling": True})