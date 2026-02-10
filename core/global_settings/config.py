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
    
    
class SERVICE_STATUS_CHOICES(models.TextChoices):
    STOPPED = "stopped", _("stopped")
    QUEUED = "queued", _("queued")
    DEPLOYING = "deploying", _("deploying")
    FAILED = "failed", _("failed")
    SUCCEEDED = "succeeded", _("succeeded")
    STOPPING = "stopping", _("stopping")
    


class Config:
    php = '''
FROM php:8.2-apache
COPY . /var/www/html/
RUN docker-php-ext-install mysqli pdo pdo_mysql
EXPOSE 80
'''

    python = '''
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "app.py"]
'''

    django = '''
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
    && rm -rf /var/lib/apt/lists/*
    
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

COPY . /app

CMD ["gunicorn", "{}:application", "--bind", "0.0.0.0:8000"]
'''

    nextjs = '''
FROM node:20-alpine as builder
WORKDIR /app
COPY . .
RUN npm install && npm run build

FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./package.json
RUN npm install --omit=dev
EXPOSE 3000
CMD ["npm", "start"]
'''

    nodejs = '''
FROM node:20-alpine
WORKDIR /app
COPY . .
RUN npm install
EXPOSE 3000
CMD ["npm", "start"]
'''

    flask = '''
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
ENV FLASK_APP=app.py
CMD ["flask", "run", "--host=0.0.0.0"]
'''

    docker = '''
# Use Docker-in-Docker for advanced setups
FROM docker:dind
CMD ["dockerd"]
'''

    go = '''
FROM golang:1.21-alpine
WORKDIR /app
COPY . .
RUN go build -o main .
EXPOSE 8080
CMD ["./main"]
'''

    static = '''
FROM nginx:alpine
COPY . /usr/share/nginx/html
EXPOSE 80
'''

    vue = '''
FROM node:20-alpine as builder
WORKDIR /app
COPY . .
RUN npm install && npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
'''

    angular = '''
FROM node:20-alpine as builder
WORKDIR /app
COPY . .
RUN npm install && npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
'''

    react = '''
FROM node:20-alpine as builder
WORKDIR /app
COPY . .
RUN npm install && npm run build

FROM nginx:alpine
COPY --from=builder /app/build /usr/share/nginx/html
EXPOSE 80
'''

    dotnet = '''
FROM mcr.microsoft.com/dotnet/aspnet:6.0 AS base
WORKDIR /app
EXPOSE 80

FROM mcr.microsoft.com/dotnet/sdk:6.0 AS build
WORKDIR /src
COPY . .
RUN dotnet publish -c Release -o /app/publish

FROM base AS final
WORKDIR /app
COPY --from=build /app/publish .
ENTRYPOINT ["dotnet", "YourAppName.dll"]
'''

