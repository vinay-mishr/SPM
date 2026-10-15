from django.urls import path

from . import views

app_name = "rate_modification"

urlpatterns = [
    path("", views.RateModificationView.as_view(), name="master"),
    path("api/", views.rate_data, name="api_data"),
    path("api/save/", views.rate_save, name="api_save"),
]
