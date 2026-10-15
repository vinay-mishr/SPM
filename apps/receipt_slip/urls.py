from django.urls import path

from . import views

app_name = "receipt_slip"

urlpatterns = [
    path("", views.ReceiptSlipEntryView.as_view(), name="entry"),
    path("stock-receipt/", views.StockReceiptView.as_view(), name="stock_receipt"),
    path("api/", views.receipt_slip_list, name="api_list"),
    path("api/next-no/", views.receipt_slip_next_no, name="api_next_no"),
    path("api/reauthenticate/", views.reauthenticate, name="api_reauthenticate"),
    path("api/save/", views.receipt_slip_save, name="api_save"),
    path("api/delete/", views.receipt_slip_delete, name="api_delete"),
    path("api/<str:mis_no>/", views.receipt_slip_detail, name="api_detail"),
    path("stock-report/", views.StockReportView.as_view(), name="stock_report"),
    path("current-stock/", views.CurrentStockView.as_view(), name="current_stock"),
    path("stock-ledger/", views.StockLedgerView.as_view(), name="stock_ledger"),
    path("production-schedule/", views.ProductionScheduleView.as_view(), name="production_schedule"),
    path("production-schedule/data/", views.production_schedule_data, name="production_schedule_data"),
    path("production-schedule/export/", views.production_schedule_export, name="production_schedule_export"),
    path("production-pending/", views.ProductionPendingView.as_view(), name="production_pending"),
    path("production-pending/data/", views.production_pending_data, name="production_pending_data"),
    path("production-pending/export/", views.production_pending_export, name="production_pending_export"),
    path("current-stock/data/", views.current_stock_data, name="current_stock_data"),
    path("current-stock/export/", views.current_stock_export, name="current_stock_export"),
    path("stock-report/data/", views.stock_report_data, name="stock_report_data"),
    path("stock-report/export/", views.stock_report_export, name="stock_report_export"),
    path("report/", views.SingleReceiptReportView.as_view(), name="single_receipt_report"),
    path("report/data/", views.single_receipt_report_data, name="single_receipt_report_data"),
    path("report/export/", views.single_receipt_report_export, name="single_receipt_report_export"),
]
