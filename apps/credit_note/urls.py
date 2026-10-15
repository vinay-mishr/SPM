from django.urls import path

from . import views
from . import narration_views

app_name = "credit_note"

urlpatterns = [
    path("", views.CreditNoteEntryView.as_view(), name="entry"),
    path("api/", views.cn_list, name="api_list"),
    path("api/next-no/", views.cn_next_no, name="api_next_no"),
    path("api/parties/", views.cn_parties, name="api_parties"),
    path("api/items/", views.cn_items, name="api_items"),
    path("api/part/", views.cn_part, name="api_part"),
    path("api/save/", views.cn_save, name="api_save"),
    path("api/delete/", views.cn_delete, name="api_delete"),
    path("api/<str:cn_no>/", views.cn_detail, name="api_detail"),
    path("print/<str:cn_no>/", views.CreditNotePrintView.as_view(), name="print"),

    path("narration/", narration_views.NarrationEntryView.as_view(), name="narration_entry"),
    path("narration/api/", narration_views.nar_list, name="narration_api_list"),
    path("narration/api/next-no/", narration_views.nar_next_no, name="narration_api_next_no"),
    path("narration/api/parties/", narration_views.nar_parties, name="narration_api_parties"),
    path("narration/api/save/", narration_views.nar_save, name="narration_api_save"),
    path("narration/api/delete/", narration_views.nar_delete, name="narration_api_delete"),
    path("narration/api/<str:cn_no>/", narration_views.nar_detail, name="narration_api_detail"),
    path("narration/print/<str:cn_no>/", narration_views.NarrationPrintView.as_view(), name="narration_print"),
]
