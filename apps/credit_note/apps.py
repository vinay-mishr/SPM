from django.apps import AppConfig


class CreditNoteConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.credit_note"
    label = "credit_note"
    verbose_name = "GST Credit Note"
