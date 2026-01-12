import os
from pathlib import Path

from dotenv import load_dotenv

from .template import  THEME_LAYOUT_DIR, THEME_VARIABLES

load_dotenv()  # take environment variables from .env.

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get("SECRET_KEY", default="")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DEBUG", 'True').lower() in ['true', 'yes', '1']

ALLOWED_HOSTS = ['*'] # os.environ.get("ALLOWED_HOSTS", "192.168.51.220:8100").split(",")
CSRF_TRUSTED_ORIGINS = [u.strip() for u in os.environ.get("CSRF_TRUSTED_ORIGINS","").split(",") if u.strip()]

# Current DJANGO_ENVIRONMENT
ENVIRONMENT = os.environ.get("DJANGO_ENVIRONMENT", default="local")


# Application definition

INSTALLED_APPS = [
    'django.contrib.sites',
    "dj_rest_auth",
    'rest_framework.authtoken',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'allauth.socialaccount.providers.nextcloud',
    "egovuz_provider",
    'rest_framework',
    'django_filters',
    'django.contrib.postgres',
    'import_export',

    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # local apps
    'ingest',
    'analytics',

]

SITE_ID = 1
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
LOGIN_URL = "account_login"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    "analytics_portal.middleware.PerUserSessionExpiryMiddleware",
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    "allauth.account.middleware.AccountMiddleware",
]



ROOT_URLCONF = 'analytics_portal.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                "django.template.context_processors.debug",
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                "analytics_portal.context_processors.my_setting",
                "analytics_portal.context_processors.environment",
            ],
            "libraries": {
                "theme": "web_project.template_tags.theme",
            },
            "builtins": [
                "django.templatetags.static",
                "web_project.template_tags.theme",
            ],
        },
    },
]

AUTHENTICATION_BACKENDS = (
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
)

# === allauth: отключаем регистрацию по email ===
ACCOUNT_ADAPTER = "analytics.adapters.NoSignupAccountAdapter"
SOCIALACCOUNT_ADAPTER = "analytics.adapters.NoSignupSocialAdapter"

# Чтобы allauth не пытался сам создавать недостающие аккаунты
SOCIALACCOUNT_AUTO_SIGNUP = False

# === allauth: логинимся по email ===
ACCOUNT_LOGIN_METHODS = {'username', 'email'}
ACCOUNT_EMAIL_REQUIRED = False
ACCOUNT_USERNAME_REQUIRED = True
ACCOUNT_SIGNUP_ENABLED = False
ACCOUNT_EMAIL_VERIFICATION = "optional"   # 'mandatory' если с подтверждением
ACCOUNT_RATE_LIMITS = {"login_failed": "5/1m;20/1h", "password_reset": "5/1h",}
ACCOUNT_SESSION_REMEMBER = True
ACCOUNT_LOGOUT_ON_PASSWORD_CHANGE = True
ACCOUNT_DEFAULT_HTTP_PROTOCOL = "http"  # на проде/в dev можно "http"

ACCOUNT_FORMS = {
    "login": "analytics.auth_form.BSLoginForm",
    #"signup": "analytics.auth_form.BSSignupForm",
    "reset_password": "analytics.auth_form.BSResetPasswordForm",
}

SOCIALACCOUNT_QUERY_EMAIL = True

SOCIALACCOUNT_LOGIN_ON_GET = True

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["email", "profile"],
        "AUTH_PARAMS": {"prompt": "select_account"},
    }
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "no-reply@miit.uz"
# на проде:
# EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
# EMAIL_HOST = "smtp.gmail.com"
# EMAIL_PORT = 587
# EMAIL_USE_TLS = True
# EMAIL_HOST_USER = "..."
# EMAIL_HOST_PASSWORD = "..."
# SOCIALACCOUNT_PROVIDERS = {
#     'google': {
#         # For each OAuth based provider, either add a ``SocialApp``
#         # (``socialaccount`` app) containing the required client
#         # credentials, or list them here:
#         'APP': {
#             'client_id': '123',
#             'secret': '456',
#             'key': ''
#         }
#     }
# }

WSGI_APPLICATION = 'analytics_portal.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": os.environ.get("DB_ENGINE"),
        "NAME": os.environ.get("DB_NAME"),
        "USER": os.environ.get("DB_USER"),
        "PASSWORD": os.environ.get("DB_PASSWORD"),
        "HOST": os.environ.get("DB_HOST"),
        "PORT": os.environ.get("DB_PORT"),
        "CONN_MAX_AGE": 600,
        "OPTIONS": {"connect_timeout": 5},

    }
}


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

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

# --- Sessions ---
SESSION_COOKIE_AGE = 30 * 60    # 30 минут
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False


USE_HTTPS = os.environ.get("USE_HTTPS", "0").lower() in ("1","true","yes")

if not DEBUG and USE_HTTPS:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

ACCOUNT_DEFAULT_HTTP_PROTOCOL = "https"
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

EGOV_BROKER_AUTHORIZE_URL = os.environ.get("EGOV_BROKER_AUTHORIZE_URL")
EGOV_BROKER_REDIRECT_URL = os.environ.get("EGOV_BROKER_REDIRECT_URL")
ONE_ID_REDIRECT_URL = os.environ.get("ONE_ID_REDIRECT_URL")

EGOV_API_TOKEN_URL = os.environ.get("EGOV_API_TOKEN_URL")
EGOV_API_BASE_URL = os.environ.get("EGOV_API_BASE_URL")
EGOV_API_BASE_URL2 = os.environ.get("EGOV_API_BASE_URL2")

EGOV_API_USERNAME = os.environ.get("EGOV_API_USERNAME")
EGOV_API_PASSWORD = os.environ.get("EGOV_API_PASSWORD")
EGOV_API_CONSUMER_KEY = os.environ.get("EGOV_API_CONSUMER_KEY")
EGOV_API_CONSUMER_SECRET = os.environ.get("EGOV_API_CONSUMER_SECRET")

# опционально
EGOV_API_TIMEOUT = int(os.environ.get("EGOV_API_TIMEOUT", "20"))


FRONTEND_AFTER_LOGIN_URL = os.environ.get(
    "BASE_URL"
)

REST_AUTH_SERIALIZERS = {
    "USER_DETAILS_SERIALIZER": "analytics.serializers.CurrentUserSerializer",
}

REST_AUTH_USER_DETAILS_SERIALIZER = "analytics.serializers.CurrentUserSerializer"

# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = "ru"

TIME_ZONE = "Asia/Tashkent"

USE_I18N = True

USE_TZ = True

# CACHES = {
#   "default": {
#     "BACKEND": "django_redis.cache.RedisCache",
#     "LOCATION": "redis://localhost:6379/1",
#     "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
#   }
# }

# --- Celery ---
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/1")

# Таймзона и UTC
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True

# Качество жизни
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = int(os.environ.get("CELERY_TASK_TIME_LIMIT", 60 * 60))  # 1h
CELERY_TASK_SOFT_TIME_LIMIT = int(os.environ.get("CELERY_TASK_SOFT_TIME_LIMIT", 55 * 60))  # 55m

# Опционально: запрет автокилла долгих задач по memory leak
CELERY_WORKER_MAX_TASKS_PER_CHILD = int(os.environ.get("CELERY_WORKER_MAX_TASKS_PER_CHILD", 100))
CELERY_WORKER_PREFETCH_MULTIPLIER = int(os.environ.get("CELERY_WORKER_PREFETCH_MULTIPLIER", 1))

# Celery Beat расписание
if os.environ.get("ENABLE_BEAT") == "1":

    CELERY_BEAT_SCHEDULE = {
        "refresh-mv": {
            "task": "analytics.tasks.refresh_materialized_views",
            "schedule": 3600,  # раз в час
            "args": (True,),   # пытаемся CONCURRENTLY
        }
    }
else:
    CELERY_BEAT_SCHEDULE = {}

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

BASE_URL = os.environ.get("BASE_URL", default="http://127.0.0.1:8000")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:8000")


EXTRACTORS = {
  "kv_pairs": [r"(?P<key>[A-Za-zА-Яа-я0-9_#\-]+)\s*[:=]\s*(?P<val>[^;,\]\)]+)"],
  "tags": [r"\[([^\]]+)\]", r"#(\w+)"]
}

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

THEME_LAYOUT_DIR = THEME_LAYOUT_DIR
THEME_VARIABLES = THEME_VARIABLES
