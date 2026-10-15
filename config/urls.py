from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.purchase_orders.views import order_share_pdf as po_order_share_pdf
from apps.purchase_orders.views import order_share_view as po_order_share_view
from apps.purchase_orders.views import pending_order_letter_share_pdf as pol_share_pdf
from apps.purchase_orders.views import pending_order_letter_share_view as pol_share_view
from apps.mrn.views import mrn_share_pdf, mrn_share_view
from apps.returnable_challan.views import challan_share_pdf, challan_share_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("masters/items/", include("apps.items.urls")),
    path("masters/parties/", include("apps.parties.urls")),
    path("masters/previous-outstanding/", include("apps.outstanding.urls")),
    path("masters/marketing-managers/", include("apps.marketing.urls")),
    path("masters/reps/", include("apps.reps.urls")),
    path("masters/supervisors/", include("apps.supervisors.urls")),
    path("masters/materials/", include("apps.materials.urls")),
    path("masters/parts/", include("apps.parts.urls")),
    path("masters/rate-modification/", include("apps.rate_modification.urls")),
    path("masters/vendors/", include("apps.vendors.urls")),
    path("masters/creditor-outstanding/", include("apps.creditor_outstanding.urls")),
    path("masters/bom/", include("apps.bom.urls")),
    path("masters/general-ledger/", include("apps.gl.urls")),
    path("masters/units/", include("apps.units.urls")),
    path("masters/gst/", include("apps.gst.urls")),
    path("purchase-order/", include("apps.purchase_orders.urls")),
    path("mrn/", include("apps.mrn.urls")),
    path("issue-slip/", include("apps.issue_slip.urls")),
    path("receipt-slip/", include("apps.receipt_slip.urls")),
    path("sale-order/", include("apps.sale_order.urls")),
    path("returnable-challan/", include("apps.returnable_challan.urls")),
    path("job-card/", include("apps.job_card.urls")),
    path("creditor-payment/", include("apps.creditor_outstanding.payment_urls")),
    path("debit-note/", include("apps.debit_note.urls")),
    path("gst-invoice/", include("apps.gst_invoice.urls")),
    path("credit-note/", include("apps.credit_note.urls")),
    path("spare-invoice/", include("apps.spare_invoice.urls")),
    path("proforma-invoice/", include("apps.proforma_invoice.urls")),
    path("proforma-spearpart/", include("apps.proforma_spearpart.urls")),
    path("quotation/", include("apps.quotations.urls")),
    path("quotation-spearpart/", include("apps.quotation_spearpart.urls")),
    path("money-receipt/", include("apps.money_receipt.urls")),
    path("po/<str:token>/", po_order_share_view, name="po_share_view"),
    path("po/<str:token>/pdf/", po_order_share_pdf, name="po_share_pdf"),
    path("reminder/<str:token>/", pol_share_view, name="pending_order_letter_share_view"),
    path("reminder/<str:token>/pdf/", pol_share_pdf, name="pending_order_letter_share_pdf"),
    path("mrn-share/<str:token>/", mrn_share_view, name="mrn_share_view"),
    path("mrn-share/<str:token>/pdf/", mrn_share_pdf, name="mrn_share_pdf"),
    path("challan-share/<str:token>/", challan_share_view, name="challan_share_view"),
    path("challan-share/<str:token>/pdf/", challan_share_pdf, name="challan_share_pdf"),
    path("", include("apps.dashboard.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
