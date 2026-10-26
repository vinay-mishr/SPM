from django.urls import path

from . import views

app_name = "vendors"
urlpatterns = [
    path("", views.VendorMasterView.as_view(), name="master"),
    path("api/", views.vendor_list, name="api_list"),
    path("api/next-code/", views.vendor_next_code, name="api_next_code"),
    path("api/gstin-lookup/", views.vendor_gstin_lookup, name="api_gstin_lookup"),
    path("api/create/", views.vendor_save, name="api_create"),
    path("api/<str:pk>/update/", views.vendor_save, name="api_update"),
    path("api/<str:pk>/delete/", views.vendor_delete, name="api_delete"),
    path("export/", views.vendor_export, name="export"),
]
