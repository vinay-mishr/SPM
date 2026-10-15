from django.urls import path

from . import views

app_name = "gst"

urlpatterns = [
    path("", views.GstMasterView.as_view(), name="master"),
    path("api/", views.gst_list, name="api_list"),
    path("api/check/", views.gst_check, name="api_check"),
    path("api/save/", views.gst_save, name="api_save"),
    path("api/<str:rate>/delete/", views.gst_delete, name="api_delete"),
]
