from django.apps import AppConfig


class MoneyReceiptConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.money_receipt"
    label = "money_receipt"
    verbose_name = "Money Receipt"
