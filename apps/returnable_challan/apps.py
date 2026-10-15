from django.apps import AppConfig


class ReturnableChallanConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.returnable_challan"
    label = "returnable_challan"
    verbose_name = "GST Returnable Challan"
