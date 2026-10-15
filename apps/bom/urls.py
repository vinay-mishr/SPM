from django.urls import path

from . import views

app_name = "bom"

urlpatterns = [
    path("", views.BomMasterView.as_view(), name="master"),
    path("api/", views.bom_list, name="api_list"),
    path("api/parts/", views.part_search, name="api_parts"),
    path("api/items/", views.item_search, name="api_items"),
    path("api/save/", views.bom_save, name="api_save"),
    path("api/<str:part_code>/delete/", views.bom_delete, name="api_delete"),
    path("api/<str:part_code>/", views.bom_detail, name="api_detail"),
    path("item/", views.BomItemMasterView.as_view(), name="item_master"),
    path("item/api/", views.bom_item_list, name="api_item_list"),
    path("item/api/save/", views.bom_item_save, name="api_item_save"),
    path("item/api/<str:item_code>/delete/", views.bom_item_delete, name="api_item_delete"),
    path("item/api/<str:item_code>/", views.bom_item_detail, name="api_item_detail"),
    path("consumption-master/", views.ConsumptionMasterView.as_view(), name="consumption_master"),
    path("consumption-master/data/", views.consumption_master_data, name="consumption_master_data"),
    path("consumption-master/export/", views.consumption_master_export, name="consumption_master_export"),
    path("without-value/", views.BomWithoutValueView.as_view(), name="without_value"),
    path("without-value/data/", views.bom_without_value_data, name="without_value_data"),
    path("without-value/export/", views.bom_without_value_export, name="without_value_export"),
    path("value-wise/", views.SaValueWiseView.as_view(), name="sa_value_wise"),
    path("value-wise/data/", views.sa_value_wise_data, name="sa_value_wise_data"),
    path("value-wise/export/", views.sa_value_wise_export, name="sa_value_wise_export"),
    path("suppliers/", views.SaSuppliersView.as_view(), name="sa_suppliers"),
    path("suppliers/data/", views.sa_suppliers_data, name="sa_suppliers_data"),
    path("suppliers/export/", views.sa_suppliers_export, name="sa_suppliers_export"),
]
