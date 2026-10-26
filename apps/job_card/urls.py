from django.urls import path

from . import pending, sub_assembly_views, views

app_name = "job_card"

urlpatterns = [
    path("", views.JobCardEntryView.as_view(), name="entry"),
    path("api/", views.job_list, name="api_list"),
    path("api/next-no/", views.job_next_no, name="api_next_no"),
    path("api/items/", views.job_items, name="api_items"),
    path("api/reauthenticate/", views.job_reauthenticate, name="api_reauthenticate"),
    path("api/save/", views.job_save, name="api_save"),
    path("api/receive/", views.job_receive, name="api_receive"),
    path("api/close/", views.job_close, name="api_close"),
    path("api/delete/", views.job_delete, name="api_delete"),
    path("listing/", views.JobCardListingView.as_view(), name="listing"),
    path("listing/data/", views.job_listing_data, name="listing_data"),
    path("listing/export/", views.job_listing_export, name="listing_export"),
    path("supervisor-listing/", views.JobCardSupervisorListingView.as_view(), name="supervisor_listing"),
    path("supervisor-listing/supervisors/", views.job_supervisors, name="supervisors"),
    path("supervisor-listing/data/", views.job_supervisor_listing_data, name="supervisor_listing_data"),
    path("supervisor-listing/export/", views.job_supervisor_listing_export, name="supervisor_listing_export"),
    path("short-list/", views.JobCardShortListView.as_view(), name="short_list"),
    path("short-list/export/", views.job_short_list_export, name="short_list_export"),
    path("product-issue/", views.ProductIssueView.as_view(), name="product_issue"),
    path("product-issue/api/", views.pi_list, name="pi_list"),
    path("product-issue/api/open-jobs/", views.pi_open_jobs, name="pi_open_jobs"),
    path("product-issue/api/preview/", views.pi_preview, name="pi_preview"),
    path("product-issue/api/save/", views.pi_save, name="pi_save"),
    path("product-issue/api/delete/", views.pi_delete, name="pi_delete"),
    path("product-issue/api/<str:serial>/", views.pi_detail, name="pi_detail"),
    path("pending-jobs/", pending.PendingJobListView.as_view(), name="pending_job_list"),
    path("pending-jobs/data/", pending.pending_job_data, name="pending_job_data"),
    path("pending-jobs/export/", pending.pending_job_export, name="pending_job_export"),
    path("sub-assembly/", sub_assembly_views.SubAssemblyEntryView.as_view(), name="sub_assembly"),
    path("sub-assembly/list/", sub_assembly_views.sa_list, name="sa_list"),
    path("sub-assembly/next-no/", sub_assembly_views.sa_next, name="sa_next"),
    path("sub-assembly/api/<str:number>/", sub_assembly_views.sa_detail, name="sa_detail"),
    path("sub-assembly/save/", sub_assembly_views.sa_save, name="sa_save"),
    path("print/",views.JobCardPrintView.as_view(), name="print"),
    path("print/<str:job_no>/", views.JobCardPrintView.as_view(), name="print_job"),
    path("api/<str:job_no>/", views.job_detail, name="api_detail"),
]
