from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from apps.parties import services as party_services
from apps.parties.choices import GstCategory, SupplyType

from . import exports, services
from .forms import VendorForm

SAVING_OFF_MESSAGE = "Saving to the SP_MACHINE database is switched off. Nothing was changed."


def _saving_off():
    return JsonResponse({"message": SAVING_OFF_MESSAGE}, status=403)


class VendorMasterView(LoginRequiredMixin, TemplateView):
    template_name = "vendors/vendor_master.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        read_only = not services.writes_enabled()
        context.update(
            initial_data={
                "vendors": services.list_vendors(),
                "company_state_code": services.company_state_code(),
                "read_only": read_only,
            },
            read_only=read_only,
            states=services.states(),
            gst_categories=GstCategory.choices,
            supply_types=SupplyType.choices,
            suggestions=services.suggestions(),
        )
        return context


@login_required
@require_GET
def vendor_list(request):
    return JsonResponse({"vendors": services.list_vendors(), "suggestions": services.suggestions()})


@login_required
@require_GET
def vendor_next_code(request):
    try:
        return JsonResponse({"code": services.next_party_code(request.GET.get("name", ""))})
    except services.PartyCodeError as exc:
        return JsonResponse({"code": "", "message": str(exc)})


@login_required
@require_GET
def vendor_gstin_lookup(request):
    """GST No. auto-fill for the Add/Modify form: reuses the Customer Master's
    provider lookup and returns only Name, Address and PIN."""
    gstin = (request.GET.get("gstin") or "").strip()
    try:
        fields = party_services.lookup_gstin_details(gstin)
    except party_services.GstinLookupError as exc:
        return JsonResponse({"message": str(exc)}, status=400)
    wanted = ("name", "address_1", "address_2", "pin")
    return JsonResponse({"fields": {key: fields[key] for key in wanted if key in fields}})


@login_required
@require_POST
def vendor_save(request, pk=None):
    if not services.writes_enabled():
        return _saving_off()
    vendor = services.get_vendor(pk) if pk else None
    if pk and vendor is None:
        raise Http404
    original = services.serialize_vendor(vendor) if vendor else None
    form = VendorForm(request.POST, original=original)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)

    try:
        if vendor:
            saved = services.update_vendor(vendor, form)
        else:
            saved = services.create_vendor(form, request.user.get_username())
    except services.PartyCodeError as exc:
        return JsonResponse({"message": str(exc)}, status=409)
    action = "updated" if vendor else "added"
    return JsonResponse(
        {"vendor": services.serialize_vendor(saved), "message": f"Vendor {saved.party_code} {action}."}
    )


@login_required
@require_POST
def vendor_delete(request, pk):
    if not services.writes_enabled():
        return _saving_off()
    vendor = services.get_vendor(pk)
    if vendor is None:
        raise Http404
    code = vendor.party_code
    try:
        services.delete_vendor(vendor)
    except services.PartyInUseError as exc:
        return JsonResponse({"message": str(exc)}, status=409)
    return JsonResponse({"message": f"Vendor {code} deleted."})


@login_required
@require_GET
def vendor_export(request):
    """CREDITOR'S PRINTING: Excel list of all Sundry Creditors, read from cust_mst."""
    vendors = exports.fetch_vendors()
    data = exports.build_workbook(vendors, settings.BRAND["name"].upper())
    response = HttpResponse(
        data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="vendor_list.xlsx"'
    return response
