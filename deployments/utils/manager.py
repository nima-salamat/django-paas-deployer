import docker
import logging
from .converter import convert_zip_to_tar, merge_tar_streams, create_dockerfile_tar
import socket
logger = logging.getLogger(__name__)

class ClientManager:
    def __init__(self):
        try:
            self.client = docker.from_env()
        except docker.errors.DockerException as e:
            logger.error(f"Failed to connect to Docker: {e}")
            self.client = None

    def get_client(self):
        return self.client

    def list_volumes(self):
        if not self.client:
            return []
        return self.client.volumes.list()

    def list_images(self):
        if not self.client:
            return []
        return self.client.images.list()

    def list_containers(self, all=True):
        if not self.client:
            return []
        return self.client.containers.list(all=all)


class ContainerManager(ClientManager):
    def __init__(self, image_name, container_name, network=None, environment=None, volumes=None, ports=None, 
                 mem_limit=None, cpu_count=None, cpu_quota=None, cpu_period=None, user="1000:1000",
                 cap_drop=["ALL"], seccomp_profile=None, read_only=True ):
        
        super().__init__()
        self.image_name = image_name
        self.container_name = container_name
        self.network = network
        self.environment = environment or {}
        self.volumes = volumes or {}
        self.ports = ports or {}
        self.mem_limit = mem_limit
        self.cpu_count = cpu_count 
        self.cpu_quota = cpu_quota
        self.cpu_period = cpu_period
        self.container = None
        self.user = user
        self.cap_drop = cap_drop
        self.seccomp_profile = seccomp_profile
        self.read_only = read_only

        if self.client:
            try:
                self.container = self.client.containers.get(container_name)
                logger.info(f"Container '{container_name}' already exists.")
            except docker.errors.NotFound:
                logger.info(f"Container '{container_name}' does not exist, ready to deploy.")

    def attach_volume(self, volume_name, mount_path="/data", mode="rw"):
        if not self.volumes:
            self.volumes = {}
        self.volumes[volume_name] = {"bind": mount_path, "mode": mode}
        logger.info(f"Volume '{volume_name}' will be mounted at '{mount_path}' with mode '{mode}'")

    def deploy(self, delete=True):
        if not self.client:
            logger.error("Docker client not initialized.")
            return None

        if self.container:
            if not delete:
                logger.warning(f"Container '{self.container_name}' already deployed.")
                return self.container
            else:
                self.remove()

        try:
            self.container = self.client.containers.run(
            image=self.image_name,
            name=self.container_name,
            volumes=self.volumes,
            ports=self.ports,
            detach=True,
            network=self.network,
            environment=self.enviorment,
            mem_limit=self.mem_limit,
            cpu_count=self.cpu_count,
            cpu_quota=self.cpu_quota,
            cpu_period=self.cpu_period,
            user=self.user,
            cap_drop=self.cap_drop,
            read_only=self.read_only,
            security_opt=["seccomp=default"],
            ipc_mode="private",
            pid_mode="private",
        )
            logger.info(f"Container '{self.container_name}' deployed successfully.")
            return self.container
        except docker.errors.ContainerError as e:
            logger.error(f"Container error: {e}")
        except docker.errors.ImageNotFound as e:
            logger.error(f"Image not found: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during deploy: {e}")
        return None

    def load(self):
        if not self.container:
            logger.error("Container not initialized.")
            return None
        try:
            self.container.reload()
            return self.container
        except docker.errors.APIError as e:
            logger.error(f"Failed to reload container: {e}")
            return None

    def status(self):
        c = self.load()
        if c:
            return c.status
        return None

    def stop(self):
        c = self.load()
        if c:
            c.stop()
            logger.info(f"Container '{self.container_name}' stopped.")
            return True
        return False

    def kill(self):
        c = self.load()
        if c:
            c.kill()
            logger.info(f"Container '{self.container_name}' killed.")
            return True
        return False

    def remove(self):
        c = self.load()
        if c:
            try:
                c.remove(force=True)
                logger.info(f"Container '{self.container_name}' removed.")
                self.container = None
                return True
            except docker.errors.APIError as e:
                logger.error(f"Failed to remove container: {e}")
                return False
        logger.warning(f"Container '{self.container_name}' does not exist to remove.")
        return False

    def logs(self, tail=100):
        c = self.load()
        if c:
            return c.logs(tail=tail).decode()
        return None

    def exec(self, command):
        c = self.load()
        if c:
            result = c.exec_run(cmd=command)
            return result.output.decode()
        return None


class ImageManager(ClientManager):
    def __init__(self, project_path, tag, dockerfile_text):
        super().__init__()
        self.project_path = project_path
        self.tag = tag
        self.dockerfile_text = dockerfile_text

    def build(self, delete=True):
        if not self.client:
            logger.error("Docker client not initialized.")
            return None

        # حذف ایمیج قبلی اگر delete=True است
        if delete:
            try:
                existing_image = self.client.images.get(self.tag)
                logger.info(f"Image '{self.tag}' exists. Removing it.")
                self.client.images.remove(existing_image.id, force=True)
                logger.info(f"Image '{self.tag}' removed.")
            except docker.errors.ImageNotFound:
                logger.info(f"No existing image '{self.tag}' found.")
            except Exception as e:
                logger.error(f"Error removing image: {e}")
                return None

        try:
            zip_tar = convert_zip_to_tar(self.project_path)
            dockerfile_tar = create_dockerfile_tar(self.dockerfile_text)
            final_tar = merge_tar_streams(dockerfile_tar, zip_tar)

            image, logs = self.client.images.build(
                fileobj=final_tar,
                tag=self.tag,
                rm=True,
                custom_context=True,
                encoding="utf-8"
            )

            for log in logs:
                if 'stream' in log:
                    logger.info(log['stream'].strip())

            logger.info(f"Image '{self.tag}' built successfully.")
            return image

        except docker.errors.BuildError as build_error:
            # اگر ایمیجی ساخته شده ولی خطا داده، ایمیج ناقص حذف شود
            try:
                images = self.client.images.list(name=self.tag)
                for img in images:
                    if not img.tags or self.tag in img.tags:
                        self.client.images.remove(img.id, force=True)
                        logger.info(f"Partial image '{self.tag}' removed after build failure.")
            except Exception as e:
                logger.error(f"Failed to clean partial images after build error: {e}")

            logger.error(f"BuildError: {build_error}")
            return None

        except Exception as e:
            logger.error(f"Unexpected error during build: {e}")
            return None

    def remove(self):
        if not self.client:
            logger.error("Docker client not initialized.")
            return False
        try:
            image = self.client.images.get(self.tag)
            self.client.images.remove(image.id, force=True)
            logger.info(f"Image '{self.tag}' removed successfully.")
            return True
        except docker.errors.ImageNotFound:
            logger.warning(f"Image '{self.tag}' not found.")
            return False
        except docker.errors.APIError as e:
            logger.error(f"Failed to remove image: {e}")
            return False


class VolumeManager(ClientManager):
    def __init__(self, volume_name, size_mb):
        super().__init__()
        self.volume_name = volume_name
        self.size_mb = size_mb

    def create_volume(self, delete=False):
        if not self.client:
            logger.error("Docker client not initialized.")
            return None

        if self.get_volume():
            if delete:
                self.remove()
            else:
                logger.warning(f"Volume '{self.volume_name}' already exists.")
                return self.get_volume()

        try:
            volume = self.client.volumes.create(
                name=self.volume_name,
                driver="local",
                driver_opts={
                    "type": "tmpfs",
                    "device": "tmpfs",
                    "o": f"size={self.size_mb}m"
                }
            )
            logger.info(f"Volume '{self.volume_name}' created.")
            return volume
        except docker.errors.APIError as e:
            logger.error(f"Failed to create volume: {e}")
            return None

    def get_volume(self):
        if not self.client:
            logger.error("Docker client not initialized.")
            return None
        try:
            volume = self.client.volumes.get(self.volume_name)
            logger.info(f"Volume '{self.volume_name}' found.")
            return volume
        except docker.errors.NotFound:
            logger.warning(f"Volume '{self.volume_name}' not found.")
            return None
        except docker.errors.APIError as e:
            logger.error(f"Failed to get volume: {e}")
            return None

    def remove(self):
        if not self.client:
            logger.error("Docker client not initialized.")
            return False
        volume = self.get_volume()
        if not volume:
            logger.warning(f"Volume '{self.volume_name}' does not exist.")
            return False
        try:
            volume.remove(force=True)
            logger.info(f"Volume '{self.volume_name}' removed.")
            return True
        except docker.errors.APIError as e:
            logger.error(f"Failed to remove volume: {e}")
            return False

    def get_volume_usage(self):
        if not self.client:
            return None
        try:
            output = self.client.containers.run(
                image="alpine",
                command="du -sh /mnt",
                volumes={self.volume_name: {"bind": "/mnt", "mode": "ro"}},
                remove=True
            )
            return output.decode().strip()
        except Exception as e:
            logger.error(f"Failed to get usage for volume '{self.volume_name}': {e}")
            return None


class NetworkManager(ClientManager):
    def __init__(self, name, driver="bridge"):
        super().__init__()
        self.name = name
        self.driver = driver

    def create_network(self):
        if not self.client:
            logger.error("Docker client not initialized.")
            return None
        try:
            network = self.client.networks.create(name=self.name, driver=self.driver)
            logger.info(f"Network '{self.name}' created.")
            return network
        except docker.errors.APIError as e:
            logger.error(f"Failed to create network: {e}")
            return None

    def get_network(self):
        if not self.client:
            logger.error("Docker client not initialized.")
            return None
        try:
            network = self.client.networks.get(self.name)
            logger.info(f"Network '{self.name}' found.")
            return network
        except docker.errors.NotFound:
            logger.warning(f"Network '{self.name}' not found.")
            return None
        except docker.errors.APIError as e:
            logger.error(f"Failed to get network: {e}")
            return None
