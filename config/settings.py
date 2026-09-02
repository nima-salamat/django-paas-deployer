
from datetime import timedelta
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

import dotenv
dotenv.load_dotenv()

import os
import re

def env_bool(name, default=False):
    value = os.environ.get(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY=os.environ.get("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env_bool("DEBUG",False)
# Allow DEBUG to be boolean-like strings; default False
if isinstance(DEBUG, int):
    DEBUG = bool(DEBUG)

# setting domain name
DOMAIN_NAME = os.environ.get("DOMAIN_NAME", "")
DEPLOYMENT_DOMAIN = os.environ.get("DEPLOYMENT_DOMAIN", "local")
API_DOMAIN_NAME = os.environ.get("API_DOMAIN_NAME", "")


def _admin_path(value: str, default: str) -> str:
    """Normalize and validate an admin URL path segment from the environment."""
    value = (value or default).strip().strip("/")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,127}", value):
        raise ValueError(
            "Admin URL path must be a single URL-safe segment (3-128 chars; "
            "letters, numbers, dot, underscore, hyphen)."
        )
    return value


# Keep the two administrative surfaces behind independently configurable,
# non-obvious paths. Set these in .env; do not hard-code the public paths.
WAGTAIL_ADMIN_PATH = _admin_path(os.environ.get("WAGTAIL_ADMIN_PATH"), "control-7x9k2m")
DJANGO_ADMIN_PATH = _admin_path(os.environ.get("DJANGO_ADMIN_PATH"), "django-4p8n6v")


# Never use a wildcard host allow-list in production. Keep only explicitly
# configured public domains plus local development hosts.
ALLOWED_HOSTS = [
    host for host in {
        API_DOMAIN_NAME,
        DOMAIN_NAME,
        "localhost",
        "127.0.0.1",
    } if host
]
if DEBUG and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

CSRF_TRUSTED_ORIGINS = [
    f"https://{API_DOMAIN_NAME}",
    f"https://{DOMAIN_NAME}",

]

# send email with proxy envs
SEND_EMAIL_WITH_PROXY = env_bool( "SEND_EMAIL_WITH_PROXY", False, )
EMAIL_PROXY = os.environ.get("EMAIL_PROXY", "")

# Application definition
INSTALLED_APPS = [
    # ASGI
    "daphne",
    "channels",

    # Custom user app MUST appear before wagtail.users
    "users",

    # Wagtail
    "wagtail.contrib.forms",
    "wagtail.contrib.redirects",
    "wagtail.contrib.settings",
    "wagtail.embeds",
    "wagtail.sites",
    "config.apps.CustomWagtailUsersAppConfig",
    "wagtail.snippets",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",
    "wagtail.admin",
    "wagtail",
    "modelcluster",
    "taggit",

    # Django core
    "cms",

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
    "auth_users",
    "plans",
    "deploy",
    "deployments",
    "services",
    "core",
    "tickets.apps.TicketsConfig",
    "messenger.apps.MessengerConfig",
    "custom_emails",
    "docs.apps.DocsConfig",
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
    # Wagtail
    'wagtail.contrib.redirects.middleware.RedirectMiddleware',
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
    'PAGE_SIZE': 10,
    # Production APIs return JSON only; BrowsableAPIRenderer is intentionally
    # disabled so the framework UI is never exposed as a public API surface.
    'DEFAULT_RENDERER_CLASSES': (
        'core.api_renderers.ProductionJSONRenderer',
    ),
    'EXCEPTION_HANDLER': 'core.api_renderers.production_exception_handler',

}

# Simple jwt settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    
    'ROTATE_REFRESH_TOKENS': True,
    
    'BLACKLIST_AFTER_ROTATION': True,
    
    'UPDATE_LAST_LOGIN': False,

    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY, 
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    'JWK_URL': None,
    'LEEWAY': 0,

    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',

    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'JTI_CLAIM': 'jti',

    'TOKEN_OBTAIN_SERIALIZER': 'rest_framework_simplejwt.serializers.TokenObtainPairSerializer',
    'TOKEN_REFRESH_SERIALIZER': 'rest_framework_simplejwt.serializers.TokenRefreshSerializer',
    'TOKEN_VERIFY_SERIALIZER': 'rest_framework_simplejwt.serializers.TokenVerifySerializer',
    'TOKEN_BLACKLIST_SERIALIZER': 'rest_framework_simplejwt.serializers.TokenBlacklistSerializer',
    'SLIDING_TOKEN_OBTAIN_SERIALIZER': 'rest_framework_simplejwt.serializers.TokenObtainSlidingSerializer',
    'SLIDING_TOKEN_REFRESH_SERIALIZER': 'rest_framework_simplejwt.serializers.TokenRefreshSlidingSerializer',
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
from urllib.parse import urlsplit, urlunsplit


def _redis_db_url(base_url: str, db: int) -> str:
    """Return a Redis URL with exactly one database suffix."""
    raw = (base_url or "").strip()
    if not raw:
        raw = "redis://127.0.0.1:6379"
    if "://" not in raw:
        raw = f"redis://{raw}"
    parts = urlsplit(raw)
    path = f"/{db}"
    return urlunsplit((parts.scheme or "redis", parts.netloc, path, parts.query, parts.fragment))


_raw_redis_url = (
    os.environ.get("REDIS_URL")
    or os.environ.get("CELERY_BROKER_URL")
    or "redis://127.0.0.1:6379"
)
# Keep one canonical Redis endpoint and assign dedicated logical DBs.
REDIS_URL = _redis_db_url(_raw_redis_url, 0)

_raw_broker_url = os.environ.get("CELERY_BROKER_URL") or REDIS_URL
_raw_result_url = os.environ.get("CELERY_RESULT_BACKEND") or _redis_db_url(_raw_redis_url, 1)
CELERY_BROKER_URL = _redis_db_url(_raw_broker_url, 0)
CELERY_RESULT_BACKEND = _redis_db_url(_raw_result_url, 1)

# Make broker connectivity explicit and resilient. These settings affect
# publish/worker startup only; they do not make a broken Redis silently
# successful. The API keeps the deployment QUEUED when publishing fails.
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_CONNECTION_MAX_RETRIES = None
CELERY_BROKER_HEARTBEAT = 30
CELERY_BROKER_POOL_LIMIT = 10
CELERY_TASK_PUBLISH_RETRY = True
CELERY_TASK_PUBLISH_RETRY_POLICY = {
    "max_retries": 5,
    "interval_start": 0,
    "interval_step": 0.5,
    "interval_max": 3,
}
CELERY_TASK_DEFAULT_QUEUE = "celery"
CELERY_TASK_DEFAULT_EXCHANGE = "celery"
CELERY_TASK_DEFAULT_ROUTING_KEY = "celery"
# Keep long-running deployment work isolated from generic Celery jobs.
# Multiple deployment-worker replicas can consume this queue independently.
CELERY_TASK_ROUTES = {
    "deployments.celery.tasks.deploy": {"queue": "deployments"},
    "deployments.celery.tasks.run_db_deploy": {"queue": "deployments"},
    "deployments.celery.tasks.stop": {"queue": "operations"},
    "deployments.celery.tasks.build_base_runtime_image": {"queue": "base-images"},
}
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ACKS_LATE = True
CELERY_IMPORTS = (
    "deployments.celery.tasks",
    "core.tasks.email",
    "custom_emails.tasks",
    "messenger.tasks",
)
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers.DatabaseScheduler'
CELERY_BEAT_SCHEDULE = {
    # Lightweight pulse; the task reads the operator-configured interval from
    # Wagtail CoreSettings and throttles itself with a distributed lock.
    "monitor_services_reconciliation": {
        "task": "deployments.celery.schedules.monitor_services",
        "schedule": 5.0,
    },
    "expire_idle_shell_sessions": {
        "task": "deployments.celery.tasks.expire_idle_shell_sessions",
        "schedule": 30.0,
    },
    "messenger_deliver_scheduled_messages": {
        "task": "messenger.tasks.deliver_scheduled_messages",
        "schedule": 15.0,  # every 15s
    },
}
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': _redis_db_url(_raw_redis_url, 2),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}


# 
# Explicitly support local Vite development and configured public frontend origins.
# Keep wildcard disabled so credentialed requests have a deterministic Origin.
CORS_ALLOW_ALL_ORIGINS = False
CORS_EXPOSE_HEADERS = [
    "Content-Range",
    "Accept-Ranges",
    "Content-Length",
    "Content-Type",
    "Content-Disposition",
]
CORS_ALLOW_HEADERS = list(getattr(__import__("corsheaders.defaults", fromlist=["default_headers"]), "default_headers", [])) + [
    "range",
    "authorization",
    "content-type",
]

CORS_ALLOWED_ORIGINS = [
    origin
    for origin in {
        f"https://{DOMAIN_NAME}" if DOMAIN_NAME else "",
        f"http://{DOMAIN_NAME}" if DOMAIN_NAME else "",
        f"https://{API_DOMAIN_NAME}" if API_DOMAIN_NAME else "",
        f"http://{API_DOMAIN_NAME}" if API_DOMAIN_NAME else "",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    }
    if origin and not origin.endswith("://")
]

CORS_ALLOW_CREDENTIALS = True


RESEND_API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_ADDR = os.getenv("EMAIL_ADDR", "onboarding@resend.dev")


# ---------------------------------------------------------------------------
# Jitsi Meet (messenger calls)
# ---------------------------------------------------------------------------
# Public base URL of the Jitsi deployment used for 1:1 and group calls.
# Override via JITSI_BASE_URL in .env (e.g. https://meet.jit.si or self-hosted).
JITSI_BASE_URL = (os.environ.get("JITSI_BASE_URL") or "https://meet.jit.si").rstrip("/")


# ---------------------------------------------------------------------------
# Messenger hot-cache (Redis) — keys are per-conversation or per-user
# ---------------------------------------------------------------------------
# Latest N messages kept in Redis *per conversation* (not per user).
MESSAGE_CACHE_SIZE = int(os.environ.get("MESSAGE_CACHE_SIZE", "1000"))
# TTL for message window keys (seconds). 0 = no expiry (not recommended).
MESSAGE_CACHE_TTL = int(os.environ.get("MESSAGE_CACHE_TTL", str(6 * 3600)))
# Short-lived caches for conversation list (per user) and conv meta/participants
MESSENGER_LIST_CACHE_TTL = int(os.environ.get("MESSENGER_LIST_CACHE_TTL", "300"))
MESSENGER_CONV_CACHE_TTL = int(os.environ.get("MESSENGER_CONV_CACHE_TTL", "120"))


# ---------------------------------------------------------------------------
# Wagtail (admin panel) — production-ready defaults
# ---------------------------------------------------------------------------

# Custom user forms (no first_name/last_name on users.User)

WAGTAIL_SITE_NAME = os.environ.get("WAGTAIL_SITE_NAME", "PaaS Control Panel")
WAGTAILADMIN_BASE_URL = os.environ.get(
    "WAGTAILADMIN_BASE_URL",
    f"https://{API_DOMAIN_NAME}" if API_DOMAIN_NAME else "http://localhost:8000",
)

# Documents / images storage under MEDIA_ROOT
WAGTAILDOCS_EXTENSIONS = [
    "csv", "docx", "key", "odt", "pdf", "pptx", "rtf", "txt", "xlsx", "zip",
]
WAGTAILIMAGES_EXTENSIONS = ["gif", "jpg", "jpeg", "png", "webp", "svg"]

# Search backend (DB is fine for admin-scale; swap to Elasticsearch later if needed)
WAGTAILSEARCH_BACKENDS = {
    "default": {
        "BACKEND": "wagtail.search.backends.database",
    }
}

# Do not expose draft pages publicly in production APIs
WAGTAIL_ENABLE_UPDATE_CHECK = True
WAGTAIL_I18N_ENABLED = False

# Password required for sensitive Wagtail actions in production
WAGTAIL_PRIVATE_PASSWORD_REQUIRED = not DEBUG

# Email notifications from Wagtail admin
WAGTAILADMIN_NOTIFICATION_USE_HTML = True

# Production security hardenings when DEBUG is off
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"

# Hard server-side upload boundary for untrusted deployment archives.
DEPLOY_MAX_ZIP_BYTES = int(os.getenv("DEPLOY_MAX_ZIP_BYTES", str(100 * 1024 * 1024)))
