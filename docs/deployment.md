# Deployment and operations

- **Image build.** Use `docker/Dockerfile` (multi-stage: Vite build → Python runtime). The image includes built assets, WhiteNoise, and Gunicorn.
- **Runtime env vars.**
  - `DJANGO_SETTINGS_MODULE=config.settings.prod`
  - `SECRET_KEY` (required)
  - `DATABASE_URL` (e.g., `postgres://user:pass@host:5432/db`)
  - `ALLOWED_HOSTS` (comma-separated)
  - `CSRF_TRUSTED_ORIGINS` (comma-separated, include scheme)
  - Optional security tunables: `SECURE_HSTS_SECONDS`, `WEB_CONCURRENCY`, `GUNICORN_THREADS`, `GUNICORN_TIMEOUT`
- **Static files.** Vite outputs to `backend/static/app`; `collectstatic` runs at build. WhiteNoise serves assets; behind a CDN you can disable if offloaded.
- **Database.** Default uses Postgres (see `docker/docker-compose.yml`). Swap `DATABASE_URL` for cloud providers.
- **Health & logging.** Gunicorn logs to stdout/stderr. Add a `/health/` endpoint as needed (not included).
- **Secrets.** Do not bake secrets into images. Provide env vars at runtime via your orchestrator (Compose, Kubernetes, ECS, etc.).
- **Migrations.** Run `python manage.py migrate` at startup; add an entrypoint script or orchestration job as needed. Compose example can be extended with a `command` that runs migrations before Gunicorn.
