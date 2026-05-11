from .base import *

DEBUG = False

ALLOWED_HOSTS = ['твой-домен.рф', 'api.твой-домен.рф']

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    "https://твой-домен.рф",
    "https://www.твой-домен.рф",
]

SPECTACULAR_SETTINGS['SERVE_PERMISSIONS'] = ['rest_framework.permissions.IsAdminUser']