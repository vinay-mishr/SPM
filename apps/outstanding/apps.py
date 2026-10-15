from django.apps import AppConfig


class OutstandingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.outstanding"
    label = "outstanding"
    verbose_name = "Previous Outstanding"
