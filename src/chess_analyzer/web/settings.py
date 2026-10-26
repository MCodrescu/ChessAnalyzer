"""Local-first Django settings; production requires explicit configuration."""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("Set DJANGO_SECRET_KEY when DJANGO_DEBUG=0.")
    SECRET_KEY = "local-development-only-not-for-production"

BASIC_AUTH_USERNAME = os.environ.get("DJANGO_BASIC_AUTH_USERNAME", "")
BASIC_AUTH_PASSWORD = os.environ.get("DJANGO_BASIC_AUTH_PASSWORD", "")
if not DEBUG and (not BASIC_AUTH_USERNAME or not BASIC_AUTH_PASSWORD):
    raise ImproperlyConfigured(
        "Set DJANGO_BASIC_AUTH_USERNAME and DJANGO_BASIC_AUTH_PASSWORD "
        "for private production access."
    )

ALLOWED_HOSTS = os.environ.get(
    "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]"
).split(",")
ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS if host.strip()]
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
ROOT_URLCONF = "chess_analyzer.web.urls"
WSGI_APPLICATION = "chess_analyzer.web.wsgi.application"
ASGI_APPLICATION = "chess_analyzer.web.asgi.application"
INSTALLED_APPS = ["django.contrib.staticfiles", "chess_analyzer.web"]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "chess_analyzer.web.middleware.PrivateAccessMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.csrf"]},
    }
]
STATIC_URL = "/static/"
STATIC_ROOT = Path(os.environ.get("DJANGO_STATIC_ROOT", "staticfiles"))
STORAGES = {
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
DATA_UPLOAD_MAX_MEMORY_SIZE = 262_144
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]
SECURE_HSTS_SECONDS = 3600 if not DEBUG else 0
if os.environ.get("DJANGO_TRUST_PROXY", "0") == "1":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
