from django.conf import settings
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy

from .forms import LoginForm


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
