"""User Master logic -- the app's own login accounts, two profiles (Admin / Sales)."""
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError

User = get_user_model()


class UserMasterError(Exception):
    """A save / delete that must be refused, with a message for the user."""

    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def is_admin(user):
    """Only an Admin-profile user (or a Django superuser) may open or change
    User Master -- everyone else, Sales included, gets no access to it at all."""
    return user.is_authenticated and user.is_admin


def serialize(user):
    return {
        "id": user.pk,
        "username": user.username,
        "name": user.get_full_name() or user.username,
        "role": user.role,
        "role_label": user.get_role_display(),
        "is_active": user.is_active,
        "is_you": None,  # filled in per-request by the view (needs request.user)
    }


def list_users():
    return [serialize(u) for u in User.objects.order_by("username")]


def _clean(raw):
    return (raw or "").strip()


def _validate_common(username, role, errors):
    if not username:
        errors["username"] = "Username is required."
    elif len(username) > 150:
        errors["username"] = "Username must be at most 150 characters."
    if role not in User.Role.values:
        errors["role"] = "Choose a role."


def create(username, role, password, created_by=None):
    username = _clean(username)
    errors = {}
    _validate_common(username, role, errors)
    if not password:
        errors["password"] = "Password is required."
    else:
        try:
            validate_password(password)
        except ValidationError as exc:
            errors["password"] = " ".join(exc.messages)
    if errors:
        raise UserMasterError("Please fix the highlighted fields.", errors)

    # The form no longer asks for a name; the list falls back to the username.
    user = User(username=username, role=role)
    user.set_password(password)
    try:
        user.save(force_insert=True)
    except IntegrityError:
        raise UserMasterError(f"Username {username} already exists.", {"username": f"Username {username} already exists."})
    return user


def update(user, role, is_active, new_password=None):
    errors = {}
    _validate_common(user.username, role, errors)
    if new_password:
        try:
            validate_password(new_password, user=user)
        except ValidationError as exc:
            errors["password"] = " ".join(exc.messages)
    if errors:
        raise UserMasterError("Please fix the highlighted fields.", errors)

    user.role = role
    user.is_active = is_active
    if new_password:
        user.set_password(new_password)
    user.save()
    return user


def delete(user, acting_user):
    if user.pk == acting_user.pk:
        raise UserMasterError("You can't delete your own account while signed in as it.")
    if user.role == User.Role.ADMIN and not user.is_superuser:
        remaining_admins = User.objects.filter(role=User.Role.ADMIN).exclude(pk=user.pk).count()
        if remaining_admins == 0 and not User.objects.filter(is_superuser=True).exclude(pk=user.pk).exists():
            raise UserMasterError("Can't delete the last Admin -- there would be no one left who can manage User Master.")
    user.delete()
