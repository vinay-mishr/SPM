from django.urls import path

from . import b2b_report, b2cl_report, b2cs_report, hsn_report, views

app_name = "gst_invoice"

urlpatterns = [
    path("", views.GstInvoiceView.as_view(), name="entry"),
    path("b2b-report/", b2b_report.B2bReportView.as_view(), name="b2b_report"),
    path("b2b-report/export/", b2b_report.b2b_export, name="b2b_report_export"),
    path("b2cl-report/", b2cl_report.B2clReportView.as_view(), name="b2cl_report"),
    path("b2cl-report/export/", b2cl_report.b2cl_export, name="b2cl_report_export"),
    path("b2cs-report/", b2cs_report.B2csReportView.as_view(), name="b2cs_report"),
    path("b2cs-report/export/", b2cs_report.b2cs_export, name="b2cs_report_export"),
    path("hsn-report/", hsn_report.HsnReportView.as_view(), name="hsn_report"),
    path("hsn-report/export/", hsn_report.hsn_export, name="hsn_report_export"),
    path("api/", views.gi_list, name="api_list"),
    path("api/next-no/", views.gi_next_no, name="api_next_no"),
    path("api/items/", views.gi_items, name="api_items"),
    path("api/item/", views.gi_item, name="api_item"),
    path("api/ledgers/", views.gi_ledgers, name="api_ledgers"),
    path("api/parties/", views.gi_parties, name="api_parties"),
    path("api/party/", views.gi_party, name="api_party"),
    path("api/save/", views.gi_save, name="api_save"),
    path("api/delete/", views.gi_delete, name="api_delete"),
    path("api/<str:bill_no>/", views.gi_detail, name="api_detail"),
    path("print/<str:bill_no>/", views.GstInvoicePrintView.as_view(), name="print"),
    path("pdf/<str:bill_no>/", views.gi_pdf, name="pdf"),
    path("share/<str:bill_no>/", views.gi_share_link, name="share_link"),
]
