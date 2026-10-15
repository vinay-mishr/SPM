from django.urls import path

from . import views

app_name = "proforma_invoice"

urlpatterns = [
    path("", views.ProformaInvoiceView.as_view(), name="entry"),
    path("api/", views.pi_list, name="api_list"),
    path("api/next-no/", views.pi_next_no, name="api_next_no"),
    path("api/items/", views.pi_items, name="api_items"),
    path("api/item/", views.pi_item, name="api_item"),
    path("api/parties/", views.pi_parties, name="api_parties"),
    path("api/party/", views.pi_party, name="api_party"),
    path("api/save/", views.pi_save, name="api_save"),
    path("api/delete/", views.pi_delete, name="api_delete"),
    path("print/<str:bill_no>/", views.ProformaInvoicePrintView.as_view(), name="print"),
    path("api/<str:bill_no>/", views.pi_detail, name="api_detail"),
]
