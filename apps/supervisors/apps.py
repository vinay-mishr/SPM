from django.apps import AppConfig


class SupervisorsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.supervisors"
    label = "supervisors"
    verbose_name = "Supervisor Master"
