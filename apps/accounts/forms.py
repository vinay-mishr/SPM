from django import forms
from django.contrib.auth.forms import AuthenticationForm


class LoginForm(AuthenticationForm):
    """Django's authentication form plus a "Remember me" option."""

    remember_me = forms.BooleanField(required=False)
