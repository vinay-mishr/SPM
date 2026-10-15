# No admin registration needed for most Purchase Order data; it is managed
# entirely through the Purchase Order Master screen (apps/purchase_orders/views.py).
#
# PurchaseOrderShareLink is the exception -- it's plain Django-managed data (not
# a view onto the legacy SP_MACHINE database), and revoking a public WhatsApp
# share link before it expires needs somewhere to do that.
from django.contrib import admin

from .models import PurchaseOrderShareLink


@admin.register(PurchaseOrderShareLink)
class PurchaseOrderShareLinkAdmin(admin.ModelAdmin):
    list_display = ("token", "div", "po_no", "created_at", "expires_at", "revoked")
    list_filter = ("revoked",)
    search_fields = ("div", "po_no", "token")
    readonly_fields = ("token", "created_at")
