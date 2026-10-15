from django.urls import path

from . import advance, cheque, payment_report, payment_views, remittance, statement

app_name = "creditor_payment"

urlpatterns = [
    path("", payment_views.PaymentEntryView.as_view(), name="entry"),
    path("list/", payment_views.pay_list, name="list"),
    path("statement/", statement.OutstandingStatementView.as_view(), name="statement"),
    path("statement/data/", statement.statement_data, name="statement_data"),
    path("statement/export/", statement.statement_export, name="statement_export"),
    path("report/", statement.OutstandingReportView.as_view(), name="report"),
    path("advance/", advance.AdvanceAdjustmentView.as_view(), name="advance"),
    path("remittance/", remittance.RemittanceView.as_view(), name="remittance"),
    path("cheque/", cheque.ChequePrintingView.as_view(), name="cheque"),
    path("cheque/data/", cheque.cheque_data, name="cheque_data"),
    path("payment-report/", payment_report.PaymentReportView.as_view(), name="payment_report"),
    path("payment-report/data/", payment_report.pr_data, name="payment_report_data"),
    path("payment-report/export/", payment_report.pr_export, name="payment_report_export"),
    path("remittance/list/", remittance.remit_list, name="remittance_list"),
    path("remittance/letter/", remittance.remit_letter, name="remittance_letter"),
    path("advance/data/", advance.adv_data, name="advance_data"),
    path("advance/save/", advance.adv_save, name="advance_save"),
    path("report/data/", statement.report_data, name="report_data"),
    path("report/export/", statement.report_export, name="report_export"),
    path("detail/", payment_views.pay_detail, name="detail"),
    path("bills/", payment_views.pay_bills, name="bills"),
    path("parties/", payment_views.pay_parties, name="parties"),
    path("banks/", payment_views.pay_banks, name="banks"),
    path("save/", payment_views.pay_save, name="save"),
    path("delete/", payment_views.pay_delete, name="delete"),
]
