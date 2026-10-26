"""Accounts > Final Accounts > Data Processing (VFP "DATA PROCES..." form).

The pasted VFP source for this screen is a batch step, not a report: it
recreates a scratch table (``copy stru to trial`` -- same columns as
``gled_mst``, a brand-new physical table/file, not the master itself) and
then calls ``do trial with thisform.trundate.value`` to populate it as a
snapshot for RUN DATE, before showing "Data Processed for Final Accounts"
and closing the form. That snapshot is presumably what the (not yet built)
Balance Sheet / Profit & Loss "Final Accounts" screens would read from
instead of recomputing a trial balance from ``trans`` on every page load.

This is NOT implemented here -- flagged, not guessed. Two things are
missing that this project's own standing rule (never write to the legacy
database on an unconfirmed schema) requires before it safely could be:

  * The ``do trial with ...`` procedure itself was never pasted. Its exact
    column-by-column logic (almost certainly the same per-ledger balance
    formula apps.gl.main_trial already uses, scoped to RUN DATE -- but
    that's an inference, not a read of its actual source) is unknown.
  * Whether a ``trial`` table already exists in the real ``legacy`` SQL
    Server database with that name, what its columns are if so, and
    whether any other already-built screen depends on it, is unconfirmed.

The OK button here is wired to a real endpoint, not a dead stub, but that
endpoint returns a clear 501 explaining the above rather than silently
doing nothing or guessing at a write. Flip ``LEGACY_DATA_PROCESSING_ENABLED``
in settings (default off) once the ``trial`` table's real schema is
confirmed and the actual VFP ``trial`` procedure logic is available.
"""
from datetime import date

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView


class DataProcessingView(LoginRequiredMixin, TemplateView):
    template_name = "gl/data_processing.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["initial_data"] = {"run_date": date.today().isoformat()}
        return context


def writes_enabled():
    return getattr(settings, "LEGACY_DATA_PROCESSING_ENABLED", False)


@login_required
@require_POST
def dp_process(request):
    if not writes_enabled():
        return JsonResponse({
            "message": (
                "Data Processing is disabled until the legacy \"trial\" snapshot table's "
                "real schema and the VFP \"do trial with ...\" procedure's own logic are "
                "confirmed -- this step would otherwise be guessing at an unverified write "
                "to the legacy database. Ask the developer to confirm these before enabling it."
            ),
        }, status=501)
    # Deliberately unreachable until LEGACY_DATA_PROCESSING_ENABLED is turned
    # on by someone who has confirmed the "trial" table's real schema.
    return JsonResponse({"message": "Data Processed for Final Accounts."})
