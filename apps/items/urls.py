from django.urls import path

from . import month_wise_sale, stock_statement, views

app_name = "items"

urlpatterns = [
    path("", views.ItemMasterView.as_view(), name="master"),
    path("api/", views.item_list, name="api_list"),
    path("api/save/", views.item_save, name="api_create"),
    path("api/<str:pk>/save/", views.item_save, name="api_update"),
    path("api/<str:pk>/delete/", views.item_delete, name="api_delete"),
    path("month-wise-sale/", month_wise_sale.MonthWiseSaleView.as_view(), name="month_wise_sale"),
    path("month-wise-sale/export/", month_wise_sale.mws_export, name="month_wise_sale_export"),
    path("stock-statement/", stock_statement.StockStatementView.as_view(), name="stock_statement"),
    path("stock-statement/export/", stock_statement.ss_export, name="stock_statement_export"),
]
