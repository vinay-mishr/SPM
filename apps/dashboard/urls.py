from django.urls import path

from . import daily_sale, user_report, views

app_name = "dashboard"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("orders-overview/", views.orders_overview_data, name="orders_overview_data"),
    path("daily-sale/", daily_sale.DailySaleView.as_view(), name="daily_sale"),
    path("daily-sale/export/", daily_sale.ds_export, name="daily_sale_export"),
    path("user-report/", user_report.UserReportView.as_view(), name="user_report"),
    path("user-report/export/", user_report.ur_export, name="user_report_export"),
]
