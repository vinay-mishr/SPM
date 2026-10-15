from django.apps import AppConfig


class GlConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.gl"
    label = "gl"
    verbose_name = "General Ledger Master"
