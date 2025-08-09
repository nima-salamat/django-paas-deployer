
from deploy.models import Deploy, DEPLOY_STATUS_CHOICES
from .config import Config
from .manager import ImageManager, ContainerManager, VolumeManager, NetworkManager, NginxManager
from core.global_settings.config import PLATFORM_CHOICES
from django.utils.timezone import now


class Deployer:
    def __init__(self, deploy_id):
        
        try:
            self.deploy = Deploy.objects.get(pk=deploy_id)
        except Deploy.DoesNotExist:
            self.deploy = None
        
        self.deploy.status = DEPLOY_STATUS_CHOICES.DEPLOYING
        self.deploy.save()
        
        self.project_path = self.deploy.zip_file.path
        self.tag = self.deploy.name
        
        self.platform = self.deploy.service.plan.platform
        self.dockerfile_text = getattr(Config, self.platform, None)

        self.volumes = self.deploy.config.get("volumes")
        
        self.network = self.deploy.service.network.name
        self.name = self.deploy.service.name
        self.running = self.deploy.running
        self.max_cpu = self.deploy.service.plan.max_cpu
        self.max_ram = self.deploy.service.plan.max_cpu
        self.storage_size = self.deploy.service.plan.storage_type
        self.plan_type = self.deploy.service.plan.plan_type
        self.max_storage = self.deploy.service.plan.max_storage
        
        self.build_status = None
        self.builder = None
        
        self.container_status = None
        self.container = None  
        
    def build(self):
        self.builder = ImageManager(project_path=self.project_path, tag=self.tag, dockerfile_text= self.dockerfile_text)
        self.builder.build(delete=True)
        
    def run(self):
        self.container_manager = ContainerManager(
            image_name=self.tag,
            container_name=self.name,
            network=self.network,
            environment=self.deploy.config.get("env", {}),
            volumes={self.volume_name: {"bind": "/app/data", "mode": "rw"}} if self.volume_name else {},
            ports=self.deploy.config.get("ports", {}),
            mem_limit=f"{self.max_ram}m",
            cpu_quota=int(self.max_cpu * 100000),
            cpu_period=100000,
        )
        self.container = self.container_manager.deploy(delete=True)
        

            
        
    
    def check_network(self):
        nm = NetworkManager(self.network)
        return nm.get_network()

    def check_volumes(self):
        if all([VolumeManager(i, size_mb=self.max_storage) for i in self.volumes]):
            return True
        return False
    
    def do_all(self):
       
    
        self.build()
        if self.builder is not None:
            if self.check_network() and self.check_volumes():
                self.run()
                if self.container:
                    if self.check_container_running():
                        self.deploy.running = True
                        self.deploy.started_at = now()
                        self.deploy.save()
                        self.delete_image()
                        return True

        self.delete_image()
        return False
        
                    
    def delete_image(self): # run at the end        
            pass
            
            
    def set_nginx(self): # if plan_type if APP
        pass
    
    def set_succeeded(self):
        pass
    
    def set_failed(self): # set failed status and remove the container
        pass
    
    def check_container_is_running(self):
        container = ContainerManager(image_name="", container_name=self.name)
        if container.container is not None:
            if container.container.status == "running":
                return True
            
            
        return False