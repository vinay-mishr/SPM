# accounts module

Authentication UI and the project's user model.

## What it provides

- `accounts.User` — custom user model (currently identical to Django's `AbstractUser`).
- Login with **Remember me** — unchecked: session ends when the browser closes;
  checked: session lasts `SESSION_COOKIE_AGE`.
- Logout (POST).
- Password reset (request → email → set new password) using Django's built-in views.
- Optional **Company SSO** button, shown only when `SSO_LOGIN_URL` is set.
  The module does not implement SSO itself; point the setting at your provider's
  start URL (e.g. a django-allauth or mozilla-django-oidc login URL).

Authentication itself is Django's (`LoginView`, `AuthenticationForm`, auth backends);
this module only adds the templates, styles and the remember-me behaviour.

## URLs (`app_name = "accounts"`)

| Name                      | Path                                    |
|---------------------------|-----------------------------------------|
| `login`                   | `login/`                                |
| `logout`                  | `logout/` (POST)                        |
| `password_reset`          | `password-reset/`                       |
| `password_reset_done`     | `password-reset/sent/`                  |
| `password_reset_confirm`  | `password-reset/<uidb64>/<token>/`      |
| `password_reset_complete` | `password-reset/complete/`              |

## Files

```
templates/accounts/
  layout.html                 split-screen layout (showcase + card + footer)
  login.html                  login card
  password_reset_form.html    request reset link
  password_reset_confirm.html set new password
  auth_message.html           "email sent" / "password changed" confirmations
  includes/icons.html         inline SVG icon sprite
  email/                      password-reset email body and subject
static/accounts/
  css/login.css
  js/login.js                 show/hide password, inline validation, no double submit
  img/                        machine + category photos
```

## Images

`static/accounts/img/` holds the machine photo (`hero-machine.jpg`) and the four
category photos (`category-*.jpg`). They were cropped from the design mock-up
(`static/img/login page.jpeg`), so they are only 633×548 and 160×160 pixels.
For sharper results on large screens, replace them with higher-resolution
originals using the same file names. No code changes are needed.

The full logo is `static/img/sp-logo-full.png` (`BRAND["logo_full"]`); the compact
mark used for the favicon and footer is `static/img/sp-logo.svg` (`BRAND["logo"]`).

## Reusing in another Django project

1. Copy `apps/accounts/` into the project and add `"apps.accounts"` to `INSTALLED_APPS`.
2. Settings:
   ```python
   AUTH_USER_MODEL = "accounts.User"
   LOGIN_URL = "accounts:login"
   LOGIN_REDIRECT_URL = "<your home url name>"
   LOGOUT_REDIRECT_URL = "accounts:login"
   SSO_LOGIN_URL = ""  # optional
   BRAND = {"name": "...", "tagline": "...", "website": "...", "phone": "...", "logo": "img/logo.svg"}
   ```
   and a context processor that puts `BRAND` into templates as `brand`
   (see `config/context_processors.py`).
3. URLs: `path("accounts/", include("apps.accounts.urls"))`.
4. Templates expect a `base.html` with `fonts`, `extra_head`, `body_class` and `body`
   blocks, and `static/css/base.css` for tokens, `.btn` and `.alert`.
5. The SP Machines marketing panel is in `{% block showcase %}` of `layout.html`;
   override that block (or the template) to rebrand.

No dependency on any other SP Machines module.
