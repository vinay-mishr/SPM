from django.contrib import admin

from . import services
from .models import Item


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("item_code", "item_name_1", "item_name_2", "unit", "hsn_code", "gst_percent", "rate", "opening_balance")
    search_fields = ("item_code", "item_name_1", "item_name_2", "item_name_3", "hsn_code")
    readonly_fields = ("item_code",)

    # The table belongs to the old software: no admin writes until they're enabled.
    def has_add_permission(self, request):
        return services.writes_enabled() and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return services.writes_enabled() and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return services.writes_enabled() and super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        if not obj.item_code:
            obj.item_code = services.next_item_code()
        super().save_model(request, obj, form, change)
