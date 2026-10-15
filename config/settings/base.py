"""
Settings shared by every environment.

Anything that differs between machines (secrets, hosts, database, email)
is read from environment variables. A local ``.env`` file is loaded if present;
see ``.env.example`` for the available keys.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _load_env_file(path):
    """Load KEY=VALUE lines from ``path``. Real environment variables win."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_env_file(BASE_DIR / ".env")


def env(key, default=None):
    return os.environ.get(key, default)


def env_bool(key, default=False):
    return env(key, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(key, default=""):
    return [item.strip() for item in env(key, default).split(",") if item.strip()]


def env_int(key, default=0):
    try:
        return int(env(key, default))
    except (TypeError, ValueError):
        return default


# --- Core -------------------------------------------------------------------

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # SP Machines modules
    "apps.accounts",
    "apps.dashboard",
    "apps.items",
    "apps.parties",
    "apps.outstanding",
    "apps.marketing",
    "apps.reps",
    "apps.supervisors",
    "apps.materials",
    "apps.parts",
    "apps.rate_modification",
    "apps.vendors",
    "apps.creditor_outstanding",
    "apps.bom",
    "apps.gl",
    "apps.units",
    "apps.purchase_orders",
    "apps.gst",
    "apps.mrn",
    "apps.issue_slip",
    "apps.receipt_slip",
    "apps.sale_order",
    "apps.returnable_challan",
    "apps.job_card",
    "apps.debit_note",
    "apps.gst_invoice",
    "apps.credit_note",
    "apps.spare_invoice",
    "apps.proforma_invoice",
    "apps.proforma_spearpart",
    "apps.quotations",
    "apps.quotation_spearpart",
    "apps.money_receipt",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "config.context_processors.brand",
            ],
        },
    },
]

# --- Database ---------------------------------------------------------------
# Two connections:
#   "default" — local SQLite: Django's own tables (users, sessions, permissions)
#               and the new modules (e.g. Party Master).
#   "legacy"  — the existing SP_MACHINE SQL Server database of the old software.
#               Configured with DB_ENGINE=mssql (plus DB_NAME, DB_HOST, DB_PORT,
#               DB_USER, DB_PASSWORD, DB_DRIVER) in .env. Django never creates,
#               alters or drops tables there (see config/db_routers.py).

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": env("SQLITE_NAME", str(BASE_DIR / "db.sqlite3")),
    }
}

DB_ENGINE = env("DB_ENGINE", "")
if DB_ENGINE and not DB_ENGINE.endswith("sqlite3"):
    DATABASES["legacy"] = {
        "ENGINE": DB_ENGINE,
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST", "localhost"),
        "PORT": env("DB_PORT", ""),
        "CONN_MAX_AGE": int(env("DB_CONN_MAX_AGE", "60")),
    }
    if DB_ENGINE == "mssql":
        DATABASES["legacy"]["OPTIONS"] = {
            "driver": env("DB_DRIVER", "ODBC Driver 18 for SQL Server"),
            # ODBC Driver 18 encrypts by default; TrustServerCertificate=yes accepts the
            # server's self-signed certificate. Set a CA-signed cert on the server and
            # change this to "TrustServerCertificate=no" for full verification.
            "extra_params": env("DB_EXTRA_PARAMS", "Encrypt=yes;TrustServerCertificate=yes"),
        }

DATABASE_ROUTERS = ["config.db_routers.LegacyRouter"]

# Models stored in the legacy database, as "app_label.ModelName".
LEGACY_MODELS = {
    "items.Item", "parties.Party", "outstanding.Bill", "marketing.MarketingManager", "reps.Rep",
    "supervisors.Supervisor", "materials.Material", "parts.Part", "bom.BomComponent", "bom.BomSaComponent", "gl.Ledger",
    "creditor_outstanding.CreditorBill", "creditor_outstanding.PaymentDetail", "creditor_outstanding.LedgerVoucher", "creditor_outstanding.VoucherCounter", "creditor_outstanding.AdvanceFile",
    "units.Unit", "purchase_orders.PurchaseOrderHeader", "purchase_orders.PurchaseOrderItem",
    "purchase_orders.PartRateHistory", "purchase_orders.CreditorOut", "purchase_orders.MrnData",
    "purchase_orders.ItemMasterTransaction", "gst.GstRate",
    "mrn.MrnData", "mrn.InvNo",
    "issue_slip.IssueSlip", "issue_slip.InvNo",
    "receipt_slip.ReceiptSlip", "receipt_slip.InvNo",
    "returnable_challan.GchlHeader", "returnable_challan.GchlLine", "returnable_challan.InvNo",
    "job_card.InvNo", "job_card.JobCard", "job_card.JobLine", "job_card.StockBalance",
    "debit_note.DebitNoteBill",
    "credit_note.GcBillHeader", "credit_note.GMasterCreditLine", "credit_note.InvNo",
    "credit_note.CBillHeader",
    "quotations.QuotationHeader", "quotations.InvNo", "quotations.QuotationMeta", "quotations.QuotationSubmission",
}


# Writing (add / modify / delete) to the legacy database — approved 25 Sep 2026.
# Set LEGACY_WRITES_ENABLED=false in .env to make Item / Party Master read-only again.
LEGACY_WRITES_ENABLED = env_bool("LEGACY_WRITES_ENABLED", True)

# Tables checked before deleting from the old software's masters.
ITEM_USAGE_TABLES = [("stock", "i_code"), ("quot_dat", "i_code"), ("p_master", "i_code")]
PARTY_USAGE_TABLES = [
    ("order", "p_code"), ("bill", "p_code"), ("cr_out", "p_code"), ("chq_file", "p_code"),
    ("p_col", "p_code"), ("mrn_dat", "p_code"), ("quot_mst", "p_code"),
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Authentication -----------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard:home"
LOGOUT_REDIRECT_URL = "accounts:login"

# How long a "Remember me" session lasts (seconds). Without it, the session
# ends when the browser closes.
SESSION_COOKIE_AGE = int(env("SESSION_COOKIE_AGE", str(60 * 60 * 24 * 14)))

# Company single sign-on entry point. The SSO button on the login page is only
# shown when this is set.
SSO_LOGIN_URL = env("SSO_LOGIN_URL", "")

# GST state code of the company (01-38). Parties in this state default to
# "(W) Within State", others to "(I) Interstate". 03 = Punjab.
COMPANY_STATE_CODE = env("COMPANY_STATE_CODE", "03")

# Ledger group codes in the old software's cust_mst.code (gled_mst):
# S001 = SUNDRY DEBTOR (old PSDCODE), S002 = SUNDRY CREDITOR (old PSCCODE).
PARTY_DEBTOR_CODE = env("PARTY_DEBTOR_CODE", "S001")

# How long a public "view this Purchase Order" share link (used for WhatsApp
# sharing) stays valid before it needs to be re-generated. A link can also be
# revoked immediately at any time via its "revoked" flag (Django admin).
PO_SHARE_LINK_EXPIRY_DAYS = env_int("PO_SHARE_LINK_EXPIRY_DAYS", 30)
PARTY_CREDITOR_CODE = env("PARTY_CREDITOR_CODE", "S002")

# --- Branding (exposed to templates as ``brand``) ------------------------------

BRAND = {
    "name": env("SITE_NAME", "SP Machines"),
    "tagline": env("SITE_TAGLINE", "Complete Packaging Solutions"),
    "website": env("SITE_WEBSITE", "https://www.spmachines.in"),
    "phone": env("SITE_PHONE", "+91 96481 69281"),
    "logo": "img/sp-logo.svg",  # compact mark: favicon, footer
    "logo_full": "img/sp-logo-full.png",  # full lockup: login page
    # Printed-document-only fields (Purchase Order header etc.) -- separate from
    # the "phone" above, which is the general in-app contact number used across the
    # rest of the site and left untouched. Override any of these with the matching
    # env var without touching code; confirm GSTIN against the certificate before
    # relying on this default.
    "address_line1": env("SITE_ADDRESS_LINE1", "Plot no. C-44, Industrial Area, Phase-3"),
    "address_line2": env("SITE_ADDRESS_LINE2", "Mohali-160055, Punjab, INDIA"),
    "print_mobile": env("SITE_PRINT_MOBILE", "7986332749"),
    "email": env("SITE_EMAIL", "spmachines@yahoo.com, spmachines9@gmail.com"),
    "gstin": env("SITE_GSTIN", "03BKVPK3084Q1ZD"),  # override via SITE_GSTIN if this changes
}

# --- Quotation (apps.quotations) ------------------------------------------------
# Defaults filled into a new quotation; every line stays editable per quotation and
# is saved with it (quot_mst.remk..remk4 and remk5..remk8).

QUOTATION_DIV = env("QUOTATION_DIV", "SP")  # quot_mst.div (the old software's "pdv")
QUOTATION_DEFAULT_TERMS = [
    env("QUOTATION_TERM_1", "1. 50% amount paid in advance and balance before receiving the material."),
    env("QUOTATION_TERM_2", "2. Interest @ 18% will be charged if the bill is not paid within 30 days."),
    env("QUOTATION_TERM_3", "3. All disputes are subject to Mohali jurisdiction only."),
    env("QUOTATION_TERM_4", "4. Freight is extra and actual."),
    env("QUOTATION_TERM_5", "5. Duties and taxes along with will be extra and as applicable."),
]
QUOTATION_BANK = {
    "name": env("QUOTATION_BANK_NAME", "HDFC BANK"),
    "account_no": env("QUOTATION_BANK_ACCOUNT", "50200066791400"),
    "ifsc": env("QUOTATION_BANK_IFSC", "HDFC0001307"),
    "branch": env("QUOTATION_BANK_BRANCH", "MOHALI"),
}

# --- Internationalisation -----------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True

# --- Static & media -----------------------------------------------------------

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# --- Email ----------------------------------------------------------------------

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "no-reply@localhost")
