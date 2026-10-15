from django.contrib import admin

from .models import Party


@admin.register(Party)
class PartyAdmin(admin.ModelAdmin):
    """Read-only view of cust_mst in /admin — use the Party Master screen to make changes."""

    list_display = ("party_code", "name", "group_code", "city", "state_name", "gst_no", "phone_1", "active")
    list_filter = ("group_code", "state_name")
    search_fields = ("party_code", "name", "city", "gst_no", "phone_1", "mobile_1")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

