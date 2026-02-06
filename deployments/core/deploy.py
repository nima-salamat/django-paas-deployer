import tarfile
from .converter import convert_zip_to_tar
from .manager.image_manager import Image
from .manager.container_manager import Container
from .manager.network_manager import Network
from .manager.client_manager import Client
import docker
from config import Config
import os
import re



def django_read_settings_module_from_tar(tar):
    DJANGO_RE = re.compile(
        r"DJANGO_SETTINGS_MODULE\s*['\"]\s*,\s*['\"]([\w\.]+)['\"]"
    )
    for m in tar.getmembers():
        if m.name.endswith("manage.py"):
            f = tar.extractfile(m)
            if not f:
                continue

            text = f.read().decode("utf-8", errors="ignore")
            match = DJANGO_RE.search(text)
            if match:
                return match.group(1).rsplit(".", 1)[0]
    return None


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
        
    


    def deploy(self):
        tarfile = convert_zip_to_tar(self.zip_filename)
        
        if self.platform == "django":
            project_name=django_read_settings_module_from_tar(tarfile)
            if project_name is None:
                return
            self.dockerfile_text = self.dockerfile_text.format(project_name)
        
        image_name = f"{self.name}:{self.tag}"
        image = Image(self.name, self.tag, self.dockerfile_text, tarfile)
        container = Container(self.name, image_name, self.max_cpu, self.max_ram, [i[0] for i in self.networks], self.volumes, self.read_only)
        
        if Container.container_is_running(self.name):
            if Container.container_is_running(self.name):
                container.stop()
            container.remove()
        if image.check_exists(image_name):
            image.remove()
        try:
            image.create()
        except:
            image.remove()
            return
        
        
        for network_name, driver in self.networks:
            
            if not Network.network_exists(network_name):
                network = Network(network_name, driver)
                network.create()
        
        try:
            container.create()
        except:
            container.remove()
            return 
        
        container.start()

        try:
            self.setup_nginx()
        except:
            self.remove_nginx_setup()
            container.remove()
        
        
    def setup_nginx(self):
        """
        Connect deployed container to nginx network if needed,
        create nginx conf, and reload nginx.
        """
        client = Client()()
        nginx_container_name = "nginx"
        proxy_network = "proxy_net"
        conf_dir = "/etc/nginx/conf.d" 

        # Connect container to proxy network if not already
        for network_name, _ in self.networks:
            if network_name == proxy_network:
                break
        else:
            # Connect container to proxy_net
            try:
                network = client.networks.get(proxy_network)
                network.connect(self.name)
                print(f"Connected container '{self.name}' to network '{proxy_network}'")
            except docker.errors.NotFound:
                print(f"Network '{proxy_network}' not found, skipping connection.")
            except Exception as e:
                print(f"Failed to connect container to network: {e}")

        # Create nginx conf for this app
        conf_filename = f"{self.name}.conf"
        conf_content = f"""
            server {{
                listen 80;
                server_name {self.name}.local;

                location / {{
                    proxy_pass http://{self.name}:{self.port};
                    proxy_set_header Host $host;
                    proxy_set_header X-Real-IP $remote_addr;
                }}
            }}
            """
        try:
            # Copy conf into nginx container
            container = client.containers.get(nginx_container_name)
            tmpfile = f"/tmp/{conf_filename}"
            with open(tmpfile, "w") as f:
                f.write(conf_content)

            # Use docker cp to copy into nginx
            os.system(f"docker cp {tmpfile} {nginx_container_name}:{conf_dir}/{conf_filename}")
            os.remove(tmpfile)

            # Reload nginx
            container.exec_run("nginx -t && nginx -s reload")
            print(f"Nginx config for '{self.name}' created and nginx reloaded.")
        except Exception as e:
            print(f"Failed to setup nginx: {e}")
                
    
    def remove_nginx_setup(self):
        """
        Remove nginx configuration for this deployed container
        and reload nginx.
        """
        client = Client()()
        nginx_container_name = "nginx"
        proxy_network = "proxy_net"
        conf_dir = "/etc/nginx/conf.d"
        conf_filename = f"{self.name}.conf"

        try:
            container = client.containers.get(nginx_container_name)

            # Remove the nginx conf file
            exit_code, _ = container.exec_run(f"rm -f {conf_dir}/{conf_filename}")
            if exit_code == 0:
                print(f"Nginx config for '{self.name}' removed.")
            else:
                print(f"Failed to remove nginx config for '{self.name}'")

            # Reload nginx
            container.exec_run("nginx -t && nginx -s reload")
            print("Nginx reloaded after removing config.")

            # Disconnect container from proxy network
            try:
                network = client.networks.get(proxy_network)
                network.disconnect(self.name)
                print(f"Container '{self.name}' disconnected from network '{proxy_network}'")
            except docker.errors.NotFound:
                print(f"Network '{proxy_network}' not found, skipping disconnect.")
            except Exception as e:
                print(f"Failed to disconnect container from network: {e}")

        except Exception as e:
            print(f"Failed to remove nginx setup for '{self.name}': {e}")

