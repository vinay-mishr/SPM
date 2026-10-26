from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("password-reset/", views.PasswordResetView.as_view(), name="password_reset"),
    path(
        "password-reset/sent/",
        views.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "password-reset/<uidb64>/<token>/",
        views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "password-reset/complete/",
        views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    path("users/", views.UserMasterView.as_view(), name="user_master"),
    path("users/api/", views.user_list, name="api_list"),
    path("users/api/create/", views.user_save, name="api_create"),
    path("users/api/<int:pk>/update/", views.user_save, name="api_update"),
    path("users/api/<int:pk>/delete/", views.user_delete, name="api_delete"),
]
