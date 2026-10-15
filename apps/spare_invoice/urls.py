from django.urls import path

from . import views

app_name = "spare_invoice"

urlpatterns = [
    path("", views.SpareInvoiceView.as_view(), name="entry"),
    path("api/", views.si_list, name="api_list"),
    path("api/next-no/", views.si_next_no, name="api_next_no"),
    path("api/items/", views.si_items, name="api_items"),
    path("api/item/", views.si_item, name="api_item"),
    path("api/parties/", views.si_parties, name="api_parties"),
    path("api/party/", views.si_party, name="api_party"),
    path("api/save/", views.si_save, name="api_save"),
    path("api/delete/", views.si_delete, name="api_delete"),
    path("api/<str:bill_no>/", views.si_detail, name="api_detail"),
    path("print/<str:bill_no>/", views.SpareInvoicePrintView.as_view(), name="print"),
]
