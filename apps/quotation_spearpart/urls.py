from django.urls import path

from . import views

app_name = "quotation_spearpart"

urlpatterns = [
    path("", views.quotation_list, name="list"),
    path("add/", views.quotation_add, name="add"),
    path("api/parties/", views.api_parties, name="api_parties"),
    path("api/items/", views.api_items, name="api_items"),
    path("api/save/", views.api_save, name="api_save"),
    path("<str:quot_no>/edit/", views.quotation_edit, name="edit"),
    path("<str:quot_no>/view/", views.quotation_view, name="view"),
    path("<str:quot_no>/delete/", views.quotation_delete, name="delete"),
    path("<str:quot_no>/print/", views.quotation_print, name="print"),
]
