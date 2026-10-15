from django.urls import path

from . import views

app_name = "materials"

urlpatterns = [
    path("", views.MaterialMasterView.as_view(), name="master"),
    path("api/", views.material_list, name="api_list"),
    path("api/next-code/", views.material_next_code, name="api_next_code"),
    path("api/save/", views.material_save, name="api_create"),
    path("api/<str:code>/save/", views.material_save, name="api_update"),
    path("api/<str:code>/delete/", views.material_delete, name="api_delete"),
]
