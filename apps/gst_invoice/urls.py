from django.urls import path

from . import views

app_name = "gst_invoice"

urlpatterns = [
    path("", views.GstInvoiceView.as_view(), name="entry"),
    path("api/", views.gi_list, name="api_list"),
    path("api/next-no/", views.gi_next_no, name="api_next_no"),
    path("api/items/", views.gi_items, name="api_items"),
    path("api/item/", views.gi_item, name="api_item"),
    path("api/ledgers/", views.gi_ledgers, name="api_ledgers"),
    path("api/parties/", views.gi_parties, name="api_parties"),
    path("api/party/", views.gi_party, name="api_party"),
    path("api/save/", views.gi_save, name="api_save"),
    path("api/delete/", views.gi_delete, name="api_delete"),
    path("api/<str:bill_no>/", views.gi_detail, name="api_detail"),
    path("print/<str:bill_no>/", views.GstInvoicePrintView.as_view(), name="print"),
]
