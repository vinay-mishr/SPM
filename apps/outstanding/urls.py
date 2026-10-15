from django.urls import path

from . import views

app_name = "outstanding"

urlpatterns = [
    path("", views.PreviousOutstandingView.as_view(), name="master"),
    path("api/", views.bill_list, name="api_list"),
    path("api/parties/", views.party_search, name="api_parties"),
    path("api/save/", views.bill_save, name="api_save"),
    path("api/delete/", views.bill_delete, name="api_delete"),
]
