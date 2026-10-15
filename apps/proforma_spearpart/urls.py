from django.urls import path

from . import views

app_name = "proforma_spearpart"

urlpatterns = [
    path("", views.ProformaSpearpartView.as_view(), name="entry"),
    path("api/", views.pfs_list, name="api_list"),
    path("api/next-no/", views.pfs_next_no, name="api_next_no"),
    path("api/items/", views.pfs_items, name="api_items"),
    path("api/item/", views.pfs_item, name="api_item"),
    path("api/parties/", views.pfs_parties, name="api_parties"),
    path("api/party/", views.pfs_party, name="api_party"),
    path("api/save/", views.pfs_save, name="api_save"),
    path("api/delete/", views.pfs_delete, name="api_delete"),
    path("print/<str:bill_no>/", views.ProformaSpearpartPrintView.as_view(), name="print"),
    path("api/<str:bill_no>/", views.pfs_detail, name="api_detail"),
]
