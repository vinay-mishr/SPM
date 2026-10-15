from django.urls import path

from . import views

app_name = "parts"

urlpatterns = [
    path("", views.PartMasterView.as_view(), name="master"),
    path("api/", views.part_list, name="api_list"),
    path("api/parties/", views.party_search, name="api_parties"),
    path("api/save/", views.part_save, name="api_create"),
    path("api/<str:code>/save/", views.part_save, name="api_update"),
    path("api/<str:code>/delete/", views.part_delete, name="api_delete"),
    path("export/", views.part_export, name="export"),
]
