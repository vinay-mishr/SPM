from django.urls import path

from . import views

app_name = "gl"

urlpatterns = [
    path("", views.LedgerMasterView.as_view(), name="master"),
    path("api/", views.ledger_list, name="api_list"),
    path("api/next-code/", views.ledger_next_code, name="api_next_code"),
    path("api/create/", views.ledger_save, name="api_create"),
    path("api/<str:pk>/update/", views.ledger_save, name="api_update"),
    path("api/<str:pk>/delete/", views.ledger_delete, name="api_delete"),
    path("opening-balance/", views.LedgerOpeningBalanceView.as_view(), name="opening_balance"),
    path("opening-balance/data/", views.opening_balance_data, name="opening_balance_data"),
    path("opening-balance/save/", views.opening_balance_save, name="opening_balance_save"),
]
