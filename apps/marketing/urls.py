from django.urls import path

from . import sale_report, views

app_name = "marketing"

urlpatterns = [
    path("", views.MarketingManagerView.as_view(), name="master"),
    path("api/", views.manager_list, name="api_list"),
    path("api/next-code/", views.manager_next_code, name="api_next_code"),
    path("api/save/", views.manager_save, name="api_create"),
    path("api/<str:code>/save/", views.manager_save, name="api_update"),
    path("api/<str:code>/delete/", views.manager_delete, name="api_delete"),
    path("sale-report/", sale_report.MmSaleReportView.as_view(), name="sale_report"),
    path("sale-report/export/", sale_report.mms_export, name="sale_report_export"),
]
