from django.urls import path

from . import views

app_name = "creditor_outstanding"

urlpatterns = [
    path("", views.CreditorOutstandingView.as_view(), name="master"),
    path("api/", views.bill_list, name="api_list"),
    path("api/vendors/", views.vendor_search, name="api_vendors"),
    path("api/save/", views.bill_save, name="api_save"),
    path("api/delete/", views.bill_delete, name="api_delete"),
]
