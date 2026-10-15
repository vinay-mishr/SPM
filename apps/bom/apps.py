from django.apps import AppConfig


class BomConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.bom"
    label = "bom"
    verbose_name = "Bill of Material Master"
