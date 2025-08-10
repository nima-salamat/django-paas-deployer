from django.db import models
from django.utils.translation import gettext_lazy as _

APPLICATIONS = [
    'php',
    'python',
    'django', 
    'nextjs', 
    'nodejs', 
    'flask', 
    'docker', 
    'go',
    'statichtmlcss', 
    'vuejs', 
    'angular', 
    'react', 
    'dotnet', 
]

DBS = [    
    'mysql',
    'postgresql',
    'mariadb', 
    'mongodb', 
    'redis', 
    'oracle',
]

# Platform choices
PLATFORM_CHOICES = [
    ('php', 'PHP'),
    ('python', 'Python'),
    ('django', 'Django'),
    ('nextjs', 'Next.js'),
    ('nodejs', 'Node.js'),
    ('flask', 'Flask'),
    ('docker', 'Docker'),
    ('go', 'Go'),
    ('statichtmlcss', 'Static HTML/CSS'),
    ('vuejs', 'Vue.js'),
    ('angular', 'Angular'),
    ('react', 'React'),
    ('dotnet', '.NET'),
    ('mysql', 'MySQL'),
    ('postgresql', 'PostgreSQL'),
    ('mariadb', 'MariaDB'),
    ('mongodb', 'MongoDB'),
    ('redis', 'Redis'),
    ('oracle', 'Oracle'),
]

default_ports = {
    'php': 80,            
    'python': None,    
    'django': 8000,       
    'nextjs': 3000,  
    'nodejs': 3000,     
    'flask': 5000,       
    'docker': None,      
    'go': None,         
    'statichtmlcss': None, 
    'vuejs': 8080,      
    'angular': 4200,     
    'react': 3000,      
    'dotnet': 5000,   
    
    'mysql': 3306,
    'postgresql': 5432,
    'mariadb': 3306,    
    'mongodb': 27017,
    'redis': 6379,
    'oracle': 1521,
}


# defauld max apps for a service
DEFAULT_MAX_APPS = 2


class PlanTypeChoices(models.TextChoices):
    DB = "DB", _("Database")
    APP = "APP", _("Application")
    READY = "READY", _("Ready-made")


class StorageTypeChoices(models.TextChoices):
    SSD = "SSD", _("SSD")
    HDD = "HDD", _("HDD")


class NameChoices(models.TextChoices):
    BRONZE = "Bronze", _("Bronze")
    SILVER = "Silver", _("Silver")
    GOLD = "Gold", _("Gold")
    DIAMOND = "Diamond", _("Diamond")

COLORS = [
        "#1abc9c","#2ecc71","#3498db", "#9b59b6","#34495e",
        "#16a085", "#27ae60", "#2980b9", "#8e44ad", "#2c3e50",
        "#f1c40f", "#e67e22", "#e74c3c", "#ecf0f1", "#95a5a6",
        "#f39c12", "#d35400", "#c0392b", "#bdc3c7", "#7f8c8d",
        
    ]
COLOR_CHOICES = [(i,j) for i, j in enumerate(COLORS, 0)]


class PaymentChoices(models.TextChoices):
    PAYED = "PAYED"
    NOT_PAYED = "NOT_PAYED"
    CANCELED = "CANCELED"
    
    
class DEPLOY_STATUS_CHOICES(models.TextChoices):
    CREATED = "created", _("created")
    QUEUED = "queued", _("queued")
    DEPLOYING = "deploying", _("deploying")
    FAILED = "failed", _("failed")
    SUCCEEDED = "succeeded", _("succeeded")
    
