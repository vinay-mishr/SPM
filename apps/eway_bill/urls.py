from django.urls import path

from . import views

app_name = "eway_bill"

urlpatterns = [
    path("", views.EwayBillView.as_view(), name="entry"),
    path("api/", views.eb_list, name="api_list"),
    path("api/transport/", views.eb_save_transport, name="api_save_transport"),
    path("api/generate/", views.eb_generate, name="api_generate"),
    path("api/token/", views.eb_token, name="api_token"),
    path("api/<str:bill_no>/", views.eb_detail, name="api_detail"),
    path("api/<str:bill_no>/json/", views.eb_json, name="api_json"),
    path("print/<str:bill_no>/", views.EwayBillPrintView.as_view(), name="print"),
]
