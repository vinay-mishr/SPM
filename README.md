# SP Machines

Modular Django application for SP Machines — Complete Packaging Solutions.

**Stack:** Python / Django · Django templates (HTML5) · CSS3 · vanilla JavaScript.

## Quick start (development)

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env            # optional for development
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000/ — you'll be redirected to the login page.
Password-reset emails are printed to the console in development.

Run the tests:

```bash
python manage.py test apps
```

## Project layout

```
config/                 project configuration
  settings/             base.py · development.py · production.py
  context_processors.py exposes settings.BRAND to templates as {{ brand }}
apps/
  accounts/             login, logout, password reset, custom User model
  dashboard/            post-login landing page
templates/base.html     global HTML skeleton
static/css/base.css     design tokens + shared components (buttons, alerts)
static/img/sp-logo.svg  brand logo (shared)
```

Each module keeps its own `templates/<module>/` and `static/<module>/css|js|img/`.
Module-specific styles never go in `static/css/base.css`.

| Module     | Depends on          | URLs           |
|------------|---------------------|----------------|
| accounts   | Django only         | `/accounts/…`  |
| dashboard  | accounts (login)    | `/`            |

## Configuration

All environment-specific values come from environment variables (or a `.env`
file in the project root). See [.env.example](.env.example) for the full list.

- `manage.py` uses `config.settings.development`.
- `wsgi.py` / `asgi.py` use `config.settings.production`, which refuses to start
  without `DJANGO_SECRET_KEY` and `DJANGO_ALLOWED_HOSTS`.

## Production checklist

1. Set `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, database and email variables.
2. `python manage.py migrate`
3. `python manage.py collectstatic`
4. Serve with a WSGI server (gunicorn / waitress) behind HTTPS.
