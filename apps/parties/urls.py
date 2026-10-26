from django.urls import path

from . import views

app_name = "parties"

urlpatterns = [
    path("", views.PartyMasterView.as_view(), name="master"),
    path("api/", views.party_list, name="api_list"),
    path("api/next-code/", views.party_next_code, name="api_next_code"),
    path("api/gstin-lookup/", views.party_gstin_lookup, name="api_gstin_lookup"),
    path("api/save/", views.party_save, name="api_create"),
    path("api/<str:pk>/save/", views.party_save, name="api_update"),
    path("api/<str:pk>/delete/", views.party_delete, name="api_delete"),
    path("export/<str:kind>/", views.party_export, name="export"),
    path("opening-balance/", views.OpeningBalanceView.as_view(), name="opening_balance"),
    path("opening-balance/data/", views.opening_balance_data, name="opening_balance_data"),
    path("opening-balance/save/", views.opening_balance_save, name="opening_balance_save"),
]
