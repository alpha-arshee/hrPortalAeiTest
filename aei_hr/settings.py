"""
Django settings for aei_hr project.
"""

from pathlib import Path
import os
from decouple import config


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY', default='django-insecure-your-secret-key-here')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=True, cast=bool)

# ALLOWED_HOSTS = [h.strip() for h in config('ALLOWED_HOSTS', default='127.0.0.1,localhost,192.168.1.5').split(',') if h.strip()]
# # ALLOWED_HOSTS = [
# #     '192.168.1.5',  # Local network IP for testing
# # ]

ALLOWED_HOSTS = ["*"]  # Allow all hosts (not recommended for production, but simplifies testing)

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'crispy_forms',
    'crispy_bootstrap5',
    
    'accounts',
    'attendance',
    'payroll',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'aei_hr.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

WSGI_APPLICATION = 'aei_hr.wsgi.application'

# Database configuration - MongoDB with djongo
raw_mongo_env = os.environ.get('MONGO_URL') or os.environ.get('MONGO_PUBLIC_URL') or os.environ.get('MONGODB_HOST')
mongo_host = raw_mongo_env if raw_mongo_env else config('MONGODB_HOST', default='mongodb://localhost:27017')

DATABASES = {
    'default': {
        'ENGINE': 'djongo',
        'NAME': config('DB_NAME', default='aei_db'),
        'ENFORCE_SCHEMA': False,
        'CLIENT': {
            'host': mongo_host,
            'maxPoolSize': int(config('MONGODB_MAX_POOL', default=50)),
            'minPoolSize': int(config('MONGODB_MIN_POOL', default=5)),
            'maxIdleTimeMS': int(config('MONGODB_MAX_IDLE_MS', default=30000)),
            'serverSelectionTimeoutMS': int(config('MONGODB_SERVER_SELECTION_TIMEOUT_MS', default=5000)),
            'connectTimeoutMS': int(config('MONGODB_CONNECT_TIMEOUT_MS', default=10000)),
            'socketTimeoutMS': int(config('MONGODB_SOCKET_TIMEOUT_MS', default=20000)),
        }
    }
}

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

# Internationalization
LANGUAGE_CODE = 'en-us'
# Use Kolkata / India timezone for project timestamps (user requested Asia/Kolkata, UTC+05:30)
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# Use WhiteNoise to serve static files in production when not using a separate
# static files server (nginx/CDN). Compress and cache with manifest for cache busting.
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom User Model
AUTH_USER_MODEL = 'accounts.User'

# Login/Logout URLs
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'accounts:dashboard'
LOGOUT_REDIRECT_URL = 'accounts:login'

# Crispy Forms
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# Session settings
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_EXPIRE_AT_BROWSER_CLOSE = True



# # Email backend (Outlook / Office365 SMTP by default for development)
# EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
# EMAIL_HOST = config('EMAIL_HOST', default='smtp.office365.com')
# EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
# EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='admin.hrms@arshee-enginv.com')
# # Provide a default empty password so the server won't crash in dev if not set in .env
# EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
# EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)

# # Use the authenticated host user as the default sender so SMTP server
# # doesn't receive messages from 'webmaster@localhost' (which many servers reject).
# DEFAULT_FROM_EMAIL = EMAIL_HOST_USER
# SERVER_EMAIL = EMAIL_HOST_USER
# For production, configure SMTP settings


# Email backend using SendGrid API over HTTPS
EMAIL_BACKEND = "sendgrid_backend.SendgridBackend"
SENDGRID_API_KEY = config('SENDGRID_API_KEY', default='')
SENDGRID_SANDBOX_MODE_IN_DEBUG = False

DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='admin.hrms@arshee-enginv.com')
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# When True, the biometric fetch command will be executed (in background)
# after a successful user login. Set to False to disable automatic fetch-on-login.
RUN_BIOMETRIC_ON_LOGIN = True

# Production security settings (tunable via environment)
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=not DEBUG, cast=bool)
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=not DEBUG, cast=bool)
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=0, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=False, cast=bool)
SECURE_HSTS_PRELOAD = config('SECURE_HSTS_PRELOAD', default=False, cast=bool)

# Allow configuring an upstream proxy (e.g., when behind nginx/load balancer)
USE_X_FORWARDED_HOST = config('USE_X_FORWARDED_HOST', default=False, cast=bool)
if USE_X_FORWARDED_HOST:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')