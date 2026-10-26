from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.generic import TemplateView

from . import services


class HomeView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Still every screen's landing / Exit page, but the Dashboard figures are
        # Admin-only -- a Sales user just gets a plain welcome.
        ctx["show_dashboard"] = self.request.user.is_admin
        if not ctx["show_dashboard"]:
            return ctx
        ctx["sale_today"] = services.sale_of_the_day()
        ctx["recent_orders"] = services.recent_sales_orders()
        ctx["recent_invoices"] = services.recent_sales_invoices()
        ctx["low_stock"] = services.low_stock_materials()
        return ctx


@login_required
def orders_overview_data(request):
    if not request.user.is_admin:
        return JsonResponse({"message": "The Dashboard is available to Admin users only."}, status=403)
    return JsonResponse(services.orders_overview())
