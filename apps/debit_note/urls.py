from django.urls import path

from . import views

app_name = "debit_note"

from . import item_views  # noqa: E402

urlpatterns = [
    path("entry/", item_views.DebitNoteEntryView.as_view(), name="item_entry"),
    path("entry/api/", item_views.ie_list, name="ie_list"),
    path("entry/api/next-no/", item_views.ie_next_no, name="ie_next_no"),
    path("entry/api/items/", item_views.ie_items, name="ie_items"),
    path("entry/api/part/", item_views.ie_part, name="ie_part"),
    path("entry/api/save/", item_views.ie_save, name="ie_save"),
    path("entry/api/delete/", item_views.ie_delete, name="ie_delete"),
    path("entry/api/detail/<str:dn_no>/", item_views.ie_detail, name="ie_detail"),
    path("", views.DebitNoteView.as_view(), name="entry"),
    path("api/", views.dn_list, name="api_list"),
    path("api/next-no/", views.dn_next_no, name="api_next_no"),
    path("api/parties/", views.dn_parties, name="api_parties"),
    path("api/save/", views.dn_save, name="api_save"),
    path("api/delete/", views.dn_delete, name="api_delete"),
    path("api/<str:dn_no>/", views.dn_detail, name="api_detail"),
]

from . import statement as _statement  # noqa: E402

urlpatterns += [
    path("statement/", _statement.DebitNoteStatementView.as_view(), name="statement"),
    path("statement/data/", _statement.statement_data, name="statement_data"),
    path("statement/export/", _statement.statement_export, name="statement_export"),
]
