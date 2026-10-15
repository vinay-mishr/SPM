from django.urls import path

from . import views

app_name = "reps"

urlpatterns = [
    path("", views.RepMasterView.as_view(), name="master"),
    path("api/", views.rep_list, name="api_list"),
    path("api/next-code/", views.rep_next_code, name="api_next_code"),
    path("api/save/", views.rep_save, name="api_create"),
    path("api/<str:code>/save/", views.rep_save, name="api_update"),
    path("api/<str:code>/delete/", views.rep_delete, name="api_delete"),
]
