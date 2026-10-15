from django.urls import path

from . import views

app_name = "returnable_challan"

urlpatterns = [
    path("", views.ChallanEntryView.as_view(), name="entry"),
    path("api/", views.challan_list, name="api_list"),
    path("api/parties/", views.challan_parties, name="api_parties"),
    path("api/pending-for-party/", views.challan_pending_for_party, name="api_pending_for_party"),
    path("api/pending-items/<str:chl_no>/", views.challan_pending_items, name="api_pending_items"),
    path("api/next-no/", views.challan_next_no, name="api_next_no"),
    path("api/reauthenticate/", views.challan_reauthenticate, name="api_reauthenticate"),
    path("api/save/", views.challan_save, name="api_save"),
    path("api/delete/", views.challan_delete, name="api_delete"),
    path("api/<str:chl_no>/", views.challan_detail, name="api_detail"),
    path("print/<str:chl_no>/", views.ChallanPrintView.as_view(), name="print"),
    path("pdf/<str:chl_no>/", views.challan_pdf, name="pdf"),
    path("share/<str:chl_no>/", views.challan_share_link, name="share_link"),
    path("pending/", views.PendingChallanReportView.as_view(), name="pending_report"),
    path("pending/data/", views.pending_challan_data, name="pending_report_data"),
    path("pending/export/", views.pending_challan_export, name="pending_report_export"),
]
