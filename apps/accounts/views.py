from django.conf import settings
from django.contrib.auth import get_user_model, views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import Http404, JsonResponse
from django.urls import reverse_lazy
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import services
from .forms import LoginForm

User = get_user_model()


class LoginView(auth_views.LoginView):
    """Django's LoginView with the SP Machines template and "Remember me"."""

    template_name = "accounts/login.html"
    form_class = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        if not form.cleaned_data.get("remember_me"):
            # End the session when the browser closes.
            self.request.session.set_expiry(0)
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sso_login_url"] = getattr(settings, "SSO_LOGIN_URL", "")
        return context


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "accounts/password_reset_form.html"
    email_template_name = "accounts/email/password_reset_email.txt"
    subject_template_name = "accounts/email/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "accounts/auth_message.html"
    extra_context = {
        "title": "Check your email",
        "message": (
            "If an account exists for the address you entered, we've sent "
            "instructions for setting a new password. It should arrive shortly."
        ),
    }


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "accounts/auth_message.html"
    extra_context = {
        "title": "Password updated",
        "message": "Your password has been changed. You can now log in with it.",
    }


# --- User Master (own login accounts: Admin / Sales) -----------------------------------
#
# Admin-only, start to finish: a non-admin never sees this page (UserPassesTestMixin
# below denies the page itself with a 403, not just the save buttons), unlike Unit
# Master and the other masters, which show their data read-only to everyone and only
# disable Add/Modify/Delete.


def _forbidden():
    return JsonResponse({"message": "Only an Admin can change User Master."}, status=403)


class UserMasterView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = "accounts/user_master.html"
    raise_exception = True  # signed in but not Admin -> 403, not a login redirect loop

    def test_func(self):
        return services.is_admin(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        users = services.list_users()
        for u in users:
            u["is_you"] = u["id"] == self.request.user.pk
        context["initial_data"] = {"users": users, "roles": User.Role.choices}
        return context


@login_required
@require_GET
def user_list(request):
    if not services.is_admin(request.user):
        return _forbidden()
    users = services.list_users()
    for u in users:
        u["is_you"] = u["id"] == request.user.pk
    return JsonResponse({"users": users})


@login_required
@require_POST
def user_save(request, pk=None):
    if not services.is_admin(request.user):
        return _forbidden()
    user = User.objects.filter(pk=pk).first() if pk else None
    if pk and user is None:
        raise Http404
    role = request.POST.get("role", "")
    try:
        if user:
            saved = services.update(
                user, role,
                is_active=request.POST.get("is_active") == "1",
                new_password=request.POST.get("password") or None,
            )
        else:
            saved = services.create(request.POST.get("username", ""), role, request.POST.get("password", ""))
    except services.UserMasterError as exc:
        return JsonResponse({"message": str(exc), "errors": exc.errors}, status=400)
    row = services.serialize(saved)
    row["is_you"] = saved.pk == request.user.pk
    action = "updated" if user else "added"
    return JsonResponse({"user": row, "message": f"User {saved.username} {action}."})


@login_required
@require_POST
def user_delete(request, pk):
    if not services.is_admin(request.user):
        return _forbidden()
    user = User.objects.filter(pk=pk).first()
    if user is None:
        raise Http404
    username = user.username
    try:
        services.delete(user, request.user)
    except services.UserMasterError as exc:
        return JsonResponse({"message": str(exc)}, status=409)
    return JsonResponse({"message": f"User {username} deleted."})
