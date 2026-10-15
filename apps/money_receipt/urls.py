from django.urls import path

from . import views

app_name = "money_receipt"

urlpatterns = [
    path("", views.MoneyReceiptView.as_view(), name="entry"),
    path("api/", views.mr_list, name="api_list"),
    path("api/next-cash-no/", views.mr_next_cash_no, name="api_next_cash_no"),
    path("api/parties/", views.mr_parties, name="api_parties"),
    path("api/party/", views.mr_party, name="api_party"),
    path("api/ledgers/", views.mr_ledgers, name="api_ledgers"),
    path("api/save/", views.mr_save, name="api_save"),
    path("api/delete/", views.mr_delete, name="api_delete"),
    path("api/detail/", views.mr_detail, name="api_detail"),
    path("party-outstanding/", views.PartyOutstandingView.as_view(), name="party_outstanding"),
    path("party-outstanding/data/", views.party_outstanding_data, name="party_outstanding_data"),
    path("party-outstanding/export/", views.party_outstanding_export, name="party_outstanding_export"),
]
