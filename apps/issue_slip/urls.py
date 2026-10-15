from django.urls import path

from . import views

app_name = "issue_slip"

urlpatterns = [
    path("", views.IssueSlipEntryView.as_view(), name="entry"),
    path("api/", views.issue_slip_list, name="api_list"),
    path("api/next-no/", views.issue_slip_next_no, name="api_next_no"),
    path("api/reauthenticate/", views.reauthenticate, name="api_reauthenticate"),
    path("api/save/", views.issue_slip_save, name="api_save"),
    path("api/delete/", views.issue_slip_delete, name="api_delete"),
    path("api/<str:mis_no>/", views.issue_slip_detail, name="api_detail"),
    path("report/", views.SingleIssueReportView.as_view(), name="single_issue_report"),
    path("report/data/", views.single_issue_report_data, name="single_issue_report_data"),
    path("report/export/", views.single_issue_report_export, name="single_issue_report_export"),
]
