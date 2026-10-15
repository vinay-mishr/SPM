from django.urls import path

from . import views

app_name = "units"

urlpatterns = [
    path("", views.UnitMasterView.as_view(), name="master"),
    path("api/", views.unit_list, name="api_list"),
    path("api/create/", views.unit_save, name="api_create"),
    path("api/<str:pk>/update/", views.unit_save, name="api_update"),
    path("api/<str:pk>/delete/", views.unit_delete, name="api_delete"),
]
