
from datetime import timedelta
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

import dotenv
dotenv.load_dotenv()

import os 

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY=os.environ.get("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = int(os.environ.get("DEBUG", "0")) if os.environ.get("DEBUG") is not None else False
# Allow DEBUG to be boolean-like strings; default False
if isinstance(DEBUG, int):
    DEBUG = bool(DEBUG)

# setting domain name
DOMAIN_NAME = os.environ.get("DOMAIN_NAME", "")
DEPLOYMENT_DOMAIN = os.environ.get("DEPLOYMENT_DOMAIN", "local")
API_DOMAIN_NAME = os.environ.get("API_DOMAIN_NAME", "")


ALLOWED_HOSTS = ["*", "localhost", "127.0.0.1", API_DOMAIN_NAME]

CSRF_TRUSTED_ORIGINS = [
    f"https://{API_DOMAIN_NAME}",
    f"https://{DOMAIN_NAME}",

]

# Application definition
INSTALLED_APPS = [
    # ASGI
    "daphne",
    "channels",

    # Django core
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres", 

    # Third party
    "corsheaders",
    "phonenumber_field",
    "rest_framework",
    "rest_framework_simplejwt",
    "django_celery_results",
    "django_celery_beat",
    "django_bootstrap5",

    # Local apps
    "users",
    "auth_users",
    "plans",
    "deploy",
    "deployments",
    "services",
    "core",
]


MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'urls'


TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'core', 'templates'), os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# WSGI_APPLICATION = 'wsgi.application'
ASGI_APPLICATION = "asgi.application"

# Channel layers: prefer REDIS if available, else fallback to in-memory for local dev
if os.environ.get("CHANNEL_REDIS_URL") or os.environ.get("REDIS_URL"):
    channel_redis_url = os.environ.get("CHANNEL_REDIS_URL") or os.environ.get("REDIS_URL")
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [channel_redis_url]},
        }
    }
else:
    CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }

# Database

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#     }
# }


DB_NAME = os.environ.get("DB_NAME")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_HOST = os.environ.get("DB_HOST")
DB_PORT = int(os.environ.get("DB_PORT", "5432")) if os.environ.get("DB_PORT") is not None else 5432

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': DB_NAME,                      
        'USER': DB_USER,
        'PASSWORD': DB_PASSWORD,
        'HOST': DB_HOST,
        'PORT': DB_PORT,
    }
}

DEPLOYMENT_LOG_DB_ALIAS = "deployment_logs"
DATABASES[DEPLOYMENT_LOG_DB_ALIAS] = {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": os.environ.get("DEPLOYMENT_LOG_DB_NAME", "deployment_logs"),
    "USER": os.environ.get("DEPLOYMENT_LOG_DB_USER", "deployment_logs"),
    "PASSWORD": os.environ.get("DEPLOYMENT_LOG_DB_PASSWORD", ""),
    "HOST": os.environ.get("DEPLOYMENT_LOG_DB_HOST", "127.0.0.1"),
    "PORT": int(os.environ.get("DEPLOYMENT_LOG_DB_PORT", "5432")),
    "CONN_MAX_AGE": 60,
}
DATABASE_ROUTERS = ["deploy.db_router.DeploymentLogRouter"]
# DATABASE_ROUTERS = []
# Password validation


AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Rest Framework settings
REST_FRAMEWORK = {
 
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10

}

# Simple jwt settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=12),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
}

# Internationalization

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Tehran'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"

# Source directories containing static files
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# Destination used by collectstatic
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media files
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'



# String formatting of phone numbers
PHONENUMBER_DEFAULT_REGION = "IR" 
PHONENUMBER_DEFAULT_FORMAT = "INTERNATIONAL"

# Custom User model 
AUTH_USER_MODEL = "users.User"


# Celery settings
# Celery settings (use REDIS_URL if provided by environment)
REDIS_URL = os.environ.get("REDIS_URL") or os.environ.get("CELERY_BROKER_URL") or "redis://127.0.0.1:6379"
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", f"{REDIS_URL}/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", f"{REDIS_URL}/1")
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers.DatabaseScheduler'
CELERY_BEAT_SCHEDULE = {
    "monitor_services_every_minute": {
        "task": "deployments.celery.schedules.monitor_services",
        "schedule": 20.0,
    },
}
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': f'{REDIS_URL}/2',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}


# 
CORS_ALLOW_ALL_ORIGINS = True

# CORS_ALLOWED_ORIGINS = [
#     "http://localhost:3000",  # or whatever your React app runs on
# ]



RESEND_API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_ADDR = os.getenv("EMAIL_ADDR", "onboarding@resend.dev")
