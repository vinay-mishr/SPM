from django.conf import settings


class LegacyRouter:
    """
    Send the models listed in settings.LEGACY_MODELS to the "legacy" database
    (the old software's SQL Server) when it is configured; everything else uses
    "default". Migrations never run against "legacy".
    """

    alias = "legacy"

    def _is_legacy(self, model):
        return (
            self.alias in settings.DATABASES
            and model._meta.label in getattr(settings, "LEGACY_MODELS", set())
        )

    def db_for_read(self, model, **hints):
        return self.alias if self._is_legacy(model) else None

    def db_for_write(self, model, **hints):
        return self.alias if self._is_legacy(model) else None

    def allow_relation(self, obj1, obj2, **hints):
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if db == self.alias:
            return False
        return None
