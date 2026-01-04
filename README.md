# Server-driven Django + HTMX starter

This boilerplate keeps Django as the single source of truth while layering HTMX for transport, Tailwind/Preline for UI, and Alpine.js for light client state. Vite builds static assets that Django serves; Storybook documents HTML-first components. Docker images are production-ready with Gunicorn and WhiteNoise.

## Stack
- Django backend with `core` example app (models, permissions, HTMX views, server-side validation)
- HTMX for partial HTML requests; Alpine.js for UI-only validation/state; Preline UI for behaviors like modals
- Tailwind CSS compiled via Vite; assets served by Django (`STATIC_URL=/static/`, Vite outputs to `backend/static/app`)
- Storybook (HTML + Vite) for component previews
- Dockerfile + docker-compose (under `docker/`) for production-like runs (Gunicorn, Postgres)
- Icons: Heroicons (SVG-only, served via Django static files and rendered via core UI components)


## Quickstart
1. Install Python 3.11+ and Node 18+.
2. Create a virtualenv and install Python deps:
   ```bash
   cd backend
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements/dev.txt
   ```
3. Install JS deps and build assets:
   ```bash
   cd frontend
   npm install
   npm run build
   ```
4. Run migrations:
   ```bash
   cd backend
   python manage.py migrate
   python manage.py createsuperuser  # optional for admin
   ```
5. Start the dev servers (two terminals):
   ```bash
   cd frontend && npm run dev
   ```
   ```bash
   cd backend && python manage.py runserver
   ```
6. Visit `http://localhost:8000` to see the HTMX-driven task board.

## Local development helpers
- Tailwind/Vite watcher: `cd frontend && npm run dev`
- Storybook (HTML): `cd frontend && npm run storybook`
- Django tests: `pytest` (uses `config.settings.dev`)

## Docker
- Build and run locally: `docker compose -f docker/docker-compose.yml up --build`
- Image ships with Vite-built assets, WhiteNoise for static files, and Gunicorn for the app server. Configure secrets via environment (`SECRET_KEY`, `DATABASE_URL`, `ALLOWED_HOSTS`, `SECURE_*`).

## Project layout
- `backend/` — Django project (`config`), shared `core` infra, and example domain app (`tasks`)
- `frontend/` — Vite + Tailwind entry point (`src/main.js`, `src/css/styles.css`, `package.json`, `vite.config.js`)
- `frontend/storybook/` — HTML-mode Storybook config and stories (pages, layout, components)
- `docs/` — Architecture notes, state rules, deployment, testing strategy

## Notes on responsibilities
- Django owns data, permissions, and final validation. HTMX endpoints always validate server-side.
- HTMX only transports HTML fragments. Alpine.js augments UX (e.g., inline validation) but never decides business outcomes.
- Preline UI manages behavior via data attributes; avoid ad-hoc JS when a component exists.

See `docs/` for guidance on adding new components, managing UI state, and deploying safely.
