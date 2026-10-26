from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Project user model.

    Adds ``role`` (ADMIN / SALES) -- the one profile distinction this app
    actually needs for now, checked by apps.accounts.services.is_admin()
    rather than full Django groups/permissions. A Django superuser (created
    via createsuperuser) is always treated as admin regardless of this
    field, so the very first account never locks itself out of User Master.
    """

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        SALES = "SALES", "Sales"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.SALES)

    class Meta(AbstractUser.Meta):
        swappable = "AUTH_USER_MODEL"

    @property
    def is_admin(self):
        return self.is_superuser or self.role == self.Role.ADMIN

    # Screens gate access with Django permissions (e.g. quotations.view_quotationheader).
    # An Admin made in User Master is a full-access user, same as a superuser, without
    # anyone having to assign individual permissions to it.
    def has_perm(self, perm, obj=None):
        if self.is_active and self.role == self.Role.ADMIN:
            return True
        return super().has_perm(perm, obj)

    def has_module_perms(self, app_label):
        if self.is_active and self.role == self.Role.ADMIN:
            return True
        return super().has_module_perms(app_label)
