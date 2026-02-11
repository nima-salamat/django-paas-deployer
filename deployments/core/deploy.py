import tarfile
import logging
from deployments.core.converter import convert_zip_to_tar
from deployments.core.manager.image_manager import Image
from deployments.core.manager.container_manager import Container
from deployments.core.manager.network_manager import Network
from deployments.core.manager.client_manager import Client
from docker.errors import NotFound, APIError, DockerException

import os
import re
import time
import tempfile
import functools
logger = logging.getLogger()


def django_read_settings_module_from_tar(tar):
    for m in tar.getmembers():
        if m.name.endswith("manage.py"):
            f = tar.extractfile(m)
            if not f:
                continue

            text = f.read().decode("utf-8", errors="ignore")
            text = re.sub(r"#.*", "", text)
            match = re.search(
                r"os\.environ\.setdefault\s*\(\s*['\"]DJANGO_SETTINGS_MODULE['\"]\s*,\s*['\"]([\w\.]+)['\"]\s*\)",
                text,
                re.S
            )
            if match:
                return match.group(1)
            match = re.search(
                r"DJANGO_SETTINGS_MODULE\s*=\s*['\"]([\w\.]+)['\"]",
                text
            )
            if match:
                return match.group(1)

    return None


def django_find_entrypoint_from_settings(tar):
    """
    tar: tarfile.TarFile (already opened)
    returns {"type":"asgi"|"wsgi", "module":"config.asgi"} or None
    """
    settings_module = django_read_settings_module_from_tar(tar)
    if not settings_module:
        return None

    settings_path = settings_module.replace(".", "/") + ".py"

    # find member by endswith (handles subdirs like project/config/settings.py)
    member = None
    for m in tar.getmembers():
        if m.name.endswith(settings_path):
            member = m
            break
    if not member:
        return None

    f = tar.extractfile(member)
    if not f:
        return None
    text = f.read().decode("utf-8", errors="ignore")

    asgi_re = re.compile(r'(?<!\w)ASGI_APPLICATION\s*=\s*[\'"]([\w\.]+)[\'"]')
    wsgi_re = re.compile(r'(?<!\w)WSGI_APPLICATION\s*=\s*[\'"]([\w\.]+)[\'"]')

    asgi_match = asgi_re.search(text)
    if asgi_match:
        full = asgi_match.group(1)
        module = full.rsplit(".", 1)[0]
        return {"type": "asgi", "module": module}

    wsgi_match = wsgi_re.search(text)
    if wsgi_match:
        full = wsgi_match.group(1)
        module = full.rsplit(".", 1)[0]
        return {"type": "wsgi", "module": module}

    return None

def _get_docker_client():
    try:
        return Client()()
    except DockerException:
        logger.exception("Failed to create docker client from environment.")
        raise

class DeployException(Exception):
    pass

class Deploy:
    def __init__(self,name, tag, zip_filename, dockerfile_text, max_cpu, max_ram, networks, volumes, port, read_only, platform):
        self.name = name
        self.tag = tag
        self.zip_filename = zip_filename
        self.dockerfile_text = dockerfile_text
        self.max_cpu = max_cpu
        self.max_ram = max_ram
        self.networks = networks
        self.volumes = volumes
        self.port = port
        self.read_only = read_only
        self.platform = platform
        self.errors = []
        
    @staticmethod
    def safe_run(func, errors, with_raise, custom_exception):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            
            try:
                return func(*args, **kwargs)
            except Exception as e:
                errors.append(e)
                if with_raise:
                    raise custom_exception from e
        return wrapper
                
        
    def deploy(self):
        try:
            _ = lambda func, errors=self.errors, with_raise=True, custom_exception=DeployException: self.safe_run(func,errors, with_raise, custom_exception)
            
            tar_stream = _(convert_zip_to_tar)(self.zip_filename)
            
            tar_stream.seek(0)
            
            if self.platform == "django":
                entrypoint = None
                with tarfile.open(fileobj=tar_stream, mode="r:*") as tar:
                    entrypoint = django_find_entrypoint_from_settings(tar)
                if not entrypoint:
                    logging.info("project name (entrypoint) not found")
                    raise ValueError("Django project name (entrypoint) not found")
                project_module = entrypoint["module"]
                self.dockerfile_text = self.dockerfile_text.format(project_module)

            logging.info(self.dockerfile_text)
            
            image_name = f"{self.name}:{self.tag}"
            image = Image(self.name, self.tag, self.dockerfile_text, tar_stream)
            container = Container(self.name, image_name, self.max_cpu, self.max_ram, [i[0] for i in self.networks], self.volumes, self.read_only, entry_port=self.port)

            TIMEOUT = 10
            INTERVAL = 0.2 
            if _(container.exists)():
                if _(Container.container_is_running)(self.name):
                    _(container.stop)()

                    start = time.time()
                    while _(Container.container_is_running)(self.name):
                        if time.time() - start > TIMEOUT:
                            raise TimeoutError("Container did not stop within 3 seconds")
                        time.sleep(INTERVAL)

                _(container.remove)()

            if _(image.exists)():
                image.remove_all()
            
            _(image.create)()
        
            for network_name, driver in self.networks:            
                if not Network.network_exists(network_name):
                    network = Network(network_name, driver)
                    _(network.create)()
        
            _(container.create)()
            
            _(container.start)()
            
            _(self.connect_proxy_net)()
            
        except DeployException:
            pass
        except Exception as e:
            self.errors.append(e)
        finally:
            _(Image.prune_dangline_images, with_raise=False)()
            if self.errors:
                self.rollback()
            return self.errors
        
    def rollback(self):
        Deploy.remove_all(self.name)
                  

    def connect_proxy_net(self, proxy_network: str = "proxy_net", create_if_missing: bool = False) -> None:
        """
        Connect self.name (container name or id) to proxy_network if not already connected.
        If create_if_missing is True, attempt to create the network when missing.
        """
        try:
            client = _get_docker_client()
        except Exception:
            # client creation failed and already logged
            return

        # ensure container exists
        try:
            container = client.containers.get(self.name)
        except NotFound:
            logger.warning("Container '%s' not found locally; skipping network connect.", self.name)
            return
        except APIError as e:
            logger.exception("Docker API error while getting container '%s': %s", self.name, e)
            return

        # ensure network exists (or create if requested)
        try:
            network = client.networks.get(proxy_network)
        except NotFound:
            if create_if_missing:
                try:
                    network = client.networks.create(proxy_network, check_duplicate=True)
                    logger.info("Created network '%s'.", proxy_network)
                except APIError as e:
                    logger.exception("Failed to create network '%s': %s", proxy_network, e)
                    return
            else:
                logger.info("Network '%s' not found, skipping connection.", proxy_network)
                return
        except APIError as e:
            logger.exception("Docker API error while getting network '%s': %s", proxy_network, e)
            return

        # check membership using inspect (more robust)
        try:
            # network.attrs sometimes stale; use low-level inspect for consistent structure
            net_info = client.api.inspect_network(network.id if hasattr(network, "id") else proxy_network)
            containers_in_net = net_info.get("Containers") or {}
            already_connected = False
            for cid, info in containers_in_net.items():
                # compare by id (full or short) or by name
                if cid == container.id or info.get("Name") in (container.name, self.name):
                    already_connected = True
                    break

            if already_connected:
                logger.info("Container '%s' already connected to network '%s'.", self.name, proxy_network)
                return

            # not connected -> try to connect
            try:
                # network.connect accepts container id/name
                network.connect(container.id)
                logger.info("Connected container '%s' to network '%s'.", self.name, proxy_network)
            except APIError as e:
                # 409 or similar may indicate already-connected race; log and continue
                logger.exception("Failed to connect container '%s' to network '%s': %s", self.name, proxy_network, e)
        except APIError as e:
            logger.exception("Error inspecting network '%s' before connect: %s", proxy_network, e)
        except Exception as e:
            logger.exception("Unexpected error during connect_proxy_net: %s", e)


    def disconnect_proxy_net(self, proxy_network: str = "proxy_net", force: bool = False) -> None:
        """
        Disconnect self.name (container name or id) from proxy_network.
        If force=True, attempt forced disconnect.
        """
        try:
            client = _get_docker_client()
        except Exception:
            return

        # get network
        try:
            network = client.networks.get(proxy_network)
        except NotFound:
            logger.info("Network '%s' not found, skipping disconnect.", proxy_network)
            return
        except APIError as e:
            logger.exception("Docker API error while getting network '%s': %s", proxy_network, e)
            return

        # try to disconnect; network.disconnect accepts name/id even if the container object isn't local
        try:
            network.disconnect(self.name, force=force)
            logger.info("Container '%s' disconnected from network '%s'.", self.name, proxy_network)
        except APIError as e:
            # if container not attached this can raise; just log
            logger.exception("Could not disconnect '%s' from '%s': %s", self.name, proxy_network, e)
        except NotFound:
            logger.exception("Could not found container '%s' from '%s': %s", self.name, proxy_network, e)
            
        except Exception as e:
            logger.exception("Unexpected error during disconnect_proxy_net: %s", e)

    @classmethod
    def remove_all(cls, name):
        # prefer using safe defaults
        c = Container(name)  # rely on Container default args
        try:
            c.stop()
        except Exception:
            logger.exception("Error stopping container %s during remove_all", name)
    
        try:
            c.remove()
        except Exception:
            logger.exception("Error removing container %s during remove_all", name)

        i = Image(name, tag=None)
        try:
            i.remove_all(force=True)
        except Exception:
            logger.exception("Error removing images for %s", name)

    
    @classmethod
    def stop_container(cls, name):
        c=Container(name, None, None, None, [(None, None)])
        c.stop()