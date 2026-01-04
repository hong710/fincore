# Multi-stage build: compile frontend assets with Vite, then build a slim Python image.

FROM node:20-alpine AS frontend-builder
WORKDIR /app
COPY tailwind.config.js postcss.config.js ./
COPY frontend/package.json frontend/vite.config.js ./frontend/
COPY frontend/src ./frontend/src
RUN mkdir -p /app/backend/static/app
WORKDIR /app/frontend
RUN npm install --legacy-peer-deps
RUN npm run build

FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements ./backend/requirements
RUN pip install -r backend/requirements/prod.txt

COPY backend ./backend
COPY --from=frontend-builder /app/backend/static/dist ./backend/static/dist

WORKDIR /app/backend

# Provide a default secret for build-time tasks like collectstatic; override at runtime.
ARG SECRET_KEY=dummy-secret
ENV SECRET_KEY=${SECRET_KEY}
ENV DJANGO_SETTINGS_MODULE=config.settings.prod

RUN python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "-c", "gunicorn.conf.py"]
