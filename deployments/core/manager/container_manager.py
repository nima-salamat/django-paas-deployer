from os import read
from .client_manager import Client
import logging
import docker
logger = logging.getLogger(__name__)

class Container(Client):
    def __init__(self, name: str, image_name: str=None, max_cpu: float=None, max_ram: int=None, networks: list=None,
                 volumes: dict = None, read_only: bool = True, command: str = None, environment: dict = None,
                 exposed_ports: dict = None, port_bindings: dict = None, entry_port=None):
        super().__init__()
        self.name = name
        self.image_name = image_name
        self.max_cpu = max_cpu
        self.max_ram = max_ram
        self.networks = networks
        self.volumes = volumes or {}
        self.read_only = read_only
        self.command = command
        self.environment = environment or {}
        self.exposed_ports = exposed_ports or {}
        self.port_bindings = port_bindings or {}
        self.entry_port = entry_port
        

    def create(self):
        try:
            host_config = self.client.api.create_host_config(
                cpu_quota=int(self.max_cpu * 100000),
                mem_limit=f"{self.max_ram}m",
                binds=self.volumes,
                port_bindings=self.port_bindings,
                read_only=self.read_only,
                
            )
            # Networking
            endpoints_config = {net: {} for net in self.networks}
            networking_config = self.client.api.create_networking_config(endpoints_config)
            # Create container
            labels = {
                "traefik.enable": "true",
                "traefik.docker.network": "proxy_net",
                # Router
                f"traefik.http.routers.{self.name}.rule":
                    f"Host(`{self.name}.local`)",
                f"traefik.http.routers.{self.name}.entrypoints": "web",
                f"traefik.http.routers.{self.name}.service": self.name,

                # Service
                f"traefik.http.services.{self.name}.loadbalancer.server.port":
                    str(self.entry_port),
            }

            container = self.client.api.create_container(
                name=self.name,
                image=self.image_name,
                command=self.command,
                environment=self.environment,
                host_config=host_config,
                networking_config=networking_config,
                ports=self.exposed_ports, 
                labels=labels,
                
            )
            logger.info(f"Service '{self.name}' created from image '{self.image_name}' on networks {self.networks}")
            return container
        except Exception as e:
            logger.error(f"Failed to create container '{self.name}': {e}")
            raise

    def start(self):
        try:
            container = self.client.containers.get(self.name)
            container.start()
            container.reload()
            logger.info("Service '%s' started; status=%s", self.name, container.status)
        except docker.errors.NotFound:
            logger.error("Container %s not found on start()", self.name)
            raise
        except Exception:
            logger.exception("Failed to start container %s", self.name)
            raise

    def stop(self, timeout=5):
        try:
            container = self.client.containers.get(self.name)
        except docker.errors.NotFound:
            logger.info("Service '%s' does not exist, nothing to stop", self.name)
            return

        try:
            if container.status != "running":
                logger.info("Service '%s' is not running (status=%s)", self.name, container.status)
                return
            container.stop(timeout=timeout)
            logger.info("Service '%s' stopped successfully", self.name)
        except docker.errors.APIError:
            logger.exception("Docker API error while stopping container '%s'", self.name)
            raise
        
    @classmethod
    def container_is_running(cls, container_name: str) -> bool:
        client = Client().client
        try:
            container = client.containers.get(container_name)
            return container.status == "running"
        except docker.errors.NotFound:
            # Service not found
            return False
        except Exception as e:
            # Log unexpected errors
            logger.error(f"Error while checking container '{container_name}': {e}")
            raise

    def is_running(self):
        
        return Container.container_is_running(self.name)

    def get_exit_code(self):
        try:
            container = self.client.containers.get(self.name)
            container.reload()

            state = container.attrs.get("State", {})

            if state.get("Running"):
                return None

            return state.get("ExitCode")

        except docker.errors.NotFound:
            return None
        except Exception:
            return None
    
    def remove(self):
        try:
            container = self.client.containers.get(self.name)
        except docker.errors.NotFound:
            logger.info("Service '%s' not found (nothing to remove)", self.name)
            return True
        try:
            container.remove(force=True)
            logger.info("Service '%s' deleted successfully", self.name)
            return True
        except Exception:
            logger.exception("Failed to remove container '%s'", self.name)
            return False
        
    def exists(self) -> bool:
        """
        Check if a container with this name exists (running or stopped).
        """
        try:
            self.client.containers.get(self.name)
            return True
        except docker.errors.NotFound:
            return False
        except Exception as e:
            logger.error(f"Error checking existence of container '{self.name}': {e}")
            raise
    
    def get_container_stats(self):
        """
        Returns a dict with 'cpu', 'memory', 'running' for the given container.
        If the container is not running or doesn't exist, returns zeros.
        More robust: uses low-level inspect to get a fresh 'Running' flag,
        and carefully computes CPU % with fallbacks.
        """
        try:
            # Try a fresh inspect via low-level API (guarantees up-to-date State)
            try:
                info = self.client.api.inspect_container(self.name)
            except docker.errors.NotFound:
                return {'cpu': 0.0, 'memory': 0.0, 'running': 0}
            except Exception as e_inspect:
                # If inspect fails for some reason, fall back to high-level get()
                logger.debug("inspect_container failed for %s: %s", self.name, e_inspect)
                container = self.client.containers.get(self.name)
                # try to reload to get fresh status
                try:
                    container.reload()
                except Exception:
                    pass
                info = container.attrs

            state = info.get("State", {}) if isinstance(info, dict) else {}
            running_flag = state.get("Running", False)

            if not running_flag:
                # container exists but not running
                return {'cpu': 0.0, 'memory': 0.0, 'running': 0}

            # At this point container is running — fetch live stats snapshot
            # Prefer high-level object for stats
            container = None
            try:
                container = self.client.containers.get(self.name)
            except Exception:
                # fallback: we already have info from inspect; but stats require container object
                logger.debug("Could not get container object for stats; trying API stats directly")
            
            try:
                stats = container.stats(stream=False) if container is not None else self.client.api.stats(self.name, stream=False)
            except Exception as e_stats:
                logger.error("Failed to get stats for %s: %s", self.name, e_stats)
                return {'cpu': 0.0, 'memory': 0.0, 'running': 1}

            # MEMORY
            mem_usage = 0
            mem_limit = 1
            try:
                mem_stats = stats.get('memory_stats', {}) or {}
                # newer docker: memory_stats.usage and memory_stats.limit
                mem_usage = mem_stats.get('usage') or mem_stats.get('stats', {}).get('rss') or 0
                mem_limit = mem_stats.get('limit') or mem_stats.get('stats', {}).get('hierarchical_memory_limit') or 1
                # protect division by zero
                mem_percent = (mem_usage / mem_limit) * 100 if mem_limit and mem_limit > 0 else 0.0
            except Exception as e:
                logger.debug("Memory parsing error for %s: %s", self.name, e)
                mem_percent = 0.0

            # CPU
            cpu_percent = 0.0
            try:
                cpu_stats = stats.get('cpu_stats', {}) or {}
                precpu_stats = stats.get('precpu_stats', {}) or {}

                total_usage = cpu_stats.get('cpu_usage', {}).get('total_usage', 0)
                pre_total = precpu_stats.get('cpu_usage', {}).get('total_usage', 0)

                system_cpu = cpu_stats.get('system_cpu_usage', 0)
                pre_system = precpu_stats.get('system_cpu_usage', 0)

                # number of CPUs
                percpu = cpu_stats.get('cpu_usage', {}).get('percpu_usage') or []
                cpu_count = len(percpu) if isinstance(percpu, (list, tuple)) and len(percpu) > 0 else (stats.get('online_cpus') or cpu_stats.get('online_cpus') or 1)

                cpu_delta = total_usage - pre_total
                system_delta = system_cpu - pre_system

                if system_delta > 0 and cpu_delta > 0:
                    cpu_percent = (cpu_delta / system_delta) * cpu_count * 100.0
                else:
                    # first sample or missing previous stats -> fallback to 0 (expected)
                    cpu_percent = 0.0

            except Exception as e:
                logger.debug("CPU parsing error for %s: %s", self.name, e)
                cpu_percent = 0.0

            return {
                'cpu': round(float(cpu_percent), 2),
                'memory': round(float(mem_percent), 2),
                'running': 1
            }

        except docker.errors.NotFound:
            # Container not found
            return {'cpu': 0.0, 'memory': 0.0, 'running': 0}
        except Exception as e:
            logger.exception("Unexpected error getting stats for %s: %s", self.name, e)
            return {'cpu': 0.0, 'memory': 0.0, 'running': 0}
