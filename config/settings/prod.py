from decouple import Csv, config

from .base import *


DEBUG = False

ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", cast=Csv())


CORS_ALLOW_ALL_ORIGINS = False

CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="",
    cast=Csv(),
)

CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS",
    default="",
    cast=Csv(),
)


SECURE_SSL_REDIRECT = True

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

SECURE_CONTENT_TYPE_NOSNIFF = True

X_FRAME_OPTIONS = "DENY"


SPECTACULAR_SETTINGS["SERVE_PERMISSIONS"] = [
    "rest_framework.permissions.IsAdminUser",
]