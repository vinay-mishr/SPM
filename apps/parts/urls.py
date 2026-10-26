from django.urls import path

from . import party_wise_item_list, production_wise_sale, views

app_name = "parts"

urlpatterns = [
    path("", views.PartMasterView.as_view(), name="master"),
    path("api/", views.part_list, name="api_list"),
    path("api/parties/", views.party_search, name="api_parties"),
    path("api/save/", views.part_save, name="api_create"),
    path("api/<str:code>/save/", views.part_save, name="api_update"),
    path("api/<str:code>/delete/", views.part_delete, name="api_delete"),
    path("export/", views.part_export, name="export"),
    path("production-wise-sale/", production_wise_sale.ProductionWiseSaleView.as_view(), name="production_wise_sale"),
    path("production-wise-sale/export/", production_wise_sale.pws_export, name="production_wise_sale_export"),
    path("party-wise-item-list/", party_wise_item_list.PartyWiseItemListView.as_view(), name="party_wise_item_list"),
    path("party-wise-item-list/export/", party_wise_item_list.pwil_export, name="party_wise_item_list_export"),
]
