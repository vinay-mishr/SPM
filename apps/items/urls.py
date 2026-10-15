from django.urls import path

from . import views

app_name = "items"

urlpatterns = [
    path("", views.ItemMasterView.as_view(), name="master"),
    path("api/", views.item_list, name="api_list"),
    path("api/save/", views.item_save, name="api_create"),
    path("api/<str:pk>/save/", views.item_save, name="api_update"),
    path("api/<str:pk>/delete/", views.item_delete, name="api_delete"),
]
