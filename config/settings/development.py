"""Local development settings."""
from .base import *  # noqa: F401,F403
from .base import SECRET_KEY, env_list

DEBUG = True

SECRET_KEY = SECRET_KEY or "django-insecure-development-only-key"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

# Password-reset emails are printed to the console.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Static file links carry "?v=<last change time>", so the browser always loads the latest
# CSS / JS after a change instead of an old cached copy.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "config.storage.VersionedStaticFilesStorage"},
}
