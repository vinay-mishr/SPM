from django.urls import path

from . import views

app_name = "supervisors"

urlpatterns = [
    path("", views.SupervisorMasterView.as_view(), name="master"),
    path("api/", views.supervisor_list, name="api_list"),
    path("api/next-code/", views.supervisor_next_code, name="api_next_code"),
    path("api/save/", views.supervisor_save, name="api_create"),
    path("api/<str:code>/save/", views.supervisor_save, name="api_update"),
    path("api/<str:code>/delete/", views.supervisor_delete, name="api_delete"),
]
