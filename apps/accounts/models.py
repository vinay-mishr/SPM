from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """
    Project user model.

    Identical to Django's default user for now. It exists from the first
    migration so that fields (phone, department, ...) can be added later
    without swapping ``AUTH_USER_MODEL`` on a live database.
    """

    class Meta(AbstractUser.Meta):
        swappable = "AUTH_USER_MODEL"
