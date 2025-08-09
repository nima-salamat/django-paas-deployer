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
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
CMD ["gunicorn", "project.wsgi:application", "--bind", "0.0.0.0:8000"]
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

