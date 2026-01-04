from .base import *

# Development defaults keep fast feedback loops and transparent errors.
DEBUG = True

SECRET_KEY = get_env("SECRET_KEY", "local-dev-secret-key")

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

INSTALLED_APPS += ["django_extensions"] if "django_extensions" not in INSTALLED_APPS else []  # type: ignore

INTERNAL_IPS = ["127.0.0.1"]
