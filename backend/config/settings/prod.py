from .base import *

# Production settings focus on safety and observability.
DEBUG = False

SECRET_KEY = get_env("SECRET_KEY", required=True)

ALLOWED_HOSTS = [host for host in get_env("ALLOWED_HOSTS", "").split(",") if host] or ["localhost"]

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(get_env("SECURE_HSTS_SECONDS", 31536000, cast=int))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

LOGGING["root"]["level"] = "WARNING"  # type: ignore
