"""Job Card rules, from legacy JOB ENTRY (new_job, imaster, stock, partmst).

* Add: BOM of the product is issued -- each component's cur_stk drops by BOM qty x job qty
  (imaster lines stts 'S').
* Modify: header only. Closed or sub-assembly jobs cannot be changed.
* Delete: restores the issued components' stock and removes the 'S' lines and the header.
* Receive: adds to the received qty (up to the job qty); 'P' lines; sub-assembly stock grows
  by the product's first four characters, as legacy did.
* Close: only when received qty equals job qty; sets close flag, close date, waste, time taken.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db import connections, transaction
from django.db.models import F, Value
from django.db.models.functions import Coalesce

from apps.bom.models import BomComponent
from apps.items.models import Item
from apps.mrn.services import _clean
from apps.parts.models import Part

from .models import InvNo, JobCard, JobLine, StockBalance

DIV = "SP"
PERMISSION = "job_card.change_jobcard"
Q2 = Decimal("0.01")


class JobError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def _first_value(queryset):
    rows = list(queryset[:1])
    return rows[0] if rows else None


def _num(value):
    try:
        return Decimal(str(value).strip())
    except Exception:
        return None


def _highest_job_no():
    best = 0
    for raw in JobCard.objects.values_list("job_no", flat=True):
        text = (raw or "").strip()
        if text.isdigit():
            best = max(best, int(text))
    return best


def next_job_no():
    counter = list(InvNo.objects.values_list("next_jc_no", flat=True)[:1])
    counter_no = int(counter[0] or 0) if counter else 0
    return str(max(counter_no, _highest_job_no()) + 1)


def list_jobs(start, end, search=""):
    qs = JobCard.objects.filter(job_date__gte=start, job_date__lte=end)
    names = dict(Item.objects.values_list("item_code", "item_name_1"))
    term = (search or "").strip().lower()
    rows = []
    for j in qs:
        name = _clean(names.get(j.item_code)) or ""
        if term and term not in (j.job_no or "").lower() and term not in name.lower():
            continue
        rows.append({
            "key": _clean(j.job_no), "job_no": _clean(j.job_no),
            "date": j.job_date.isoformat() if j.job_date else "",
            "item_code": _clean(j.item_code), "item_name": name[:30],
            "qty": f"{(j.qty or 0):.0f}", "received": f"{(j.received_qty or 0):.0f}",
            "closed": _clean(j.close_flag) == "Y",
        })
    rows.sort(key=lambda r: (r["date"], int(r["job_no"]) if r["job_no"].isdigit() else 0), reverse=True)
    return rows


def get_job(job_no):
    j = _first_value(JobCard.objects.filter(job_no=job_no))
    if not j:
        return None
    item = _first_value(Item.objects.filter(item_code=j.item_code))
    lines = JobLine.objects.filter(job_no=job_no, status__in=["S", "P"]).values(
        "status", "part_code", "qty", "line_date")
    issued, received = [], []
    part_names = dict(Part.objects.values_list("part_number", "description_1"))
    for l in lines:
        row = {"part_code": _clean(l["part_code"]), "part_name": _clean(part_names.get(l["part_code"])) or "",
               "qty": f"{(l['qty'] or 0):.3f}", "date": l["line_date"].isoformat() if l["line_date"] else ""}
        (issued if l["status"] == "S" else received).append(row)
    return {
        "job_no": _clean(j.job_no),
        "job_date": j.job_date.isoformat() if j.job_date else "",
        "item_code": _clean(j.item_code),
        "item_name": _clean(item.item_name_1) if item else "",
        "qty": f"{(j.qty or 0):.0f}",
        "received": f"{(j.received or 0):.0f}",
        "received_qty": f"{(j.received_qty or 0):.0f}",
        "rejected": "0",
        "close_date": j.close_date.isoformat() if j.close_date else "",
        "supervisor": _clean(j.supervisor),
        "start_date": j.start_date.isoformat() if j.start_date else "",
        "time_taken": f"{(j.time_taken or 0):.2f}",
        "waste": f"{(j.waste or 0):.0f}",
        "closed": _clean(j.close_flag) == "Y",
        "sub_assembly": _clean(j.sub_assembly) == "Y",
        "issued": issued,
        "received_lines": received,
    }


def _parse_date(value):
    try:
        y, m, d = (int(x) for x in (value or "").split("-"))
        return date(y, m, d)
    except (TypeError, ValueError):
        return None


def _validate_header(payload, is_add):
    errors = {}
    job_no = (payload.get("job_no") or "").strip()
    if not job_no:
        errors["job_no"] = "Job card no. is empty."
    elif not job_no.isdigit():
        errors["job_no"] = "Job card no. must be a number."
    job_date = _parse_date(payload.get("job_date"))
    if not job_date:
        errors["job_date"] = "Job date is empty."
    if is_add:
        item_code = (payload.get("item_code") or "").strip().upper()
        if not item_code:
            errors["item_code"] = "Select a product."
        elif not Item.objects.filter(item_code=item_code).exists():
            errors["item_code"] = "Product not found in the Item Master."
        qty = _num(payload.get("qty"))
        if qty is None or qty <= 0:
            errors["qty"] = "Job qty must be greater than zero."
    if errors:
        raise JobError("Fix the highlighted fields.", errors)
    return job_no, job_date


def save_add(payload, username=""):
    with transaction.atomic(using="legacy"):
        job_no, job_date = _validate_header(payload, is_add=True)
        # Locks the single InvNo row for the rest of this transaction (same
        # select_for_update()-on-the-counter convention apps.debit_note._issue_no()
        # and friends use), so two concurrent Adds can't both pass the exists()
        # check below for the same job_no -- new_job has no real primary key/unique
        # constraint to catch that as a last resort, so this lock is the only thing
        # that can.
        InvNo.objects.select_for_update().values_list("next_jc_no", flat=True).first()
        if JobCard.objects.filter(job_no=job_no).exists():
            raise JobError("MIS NO ALREADY EXIST", {"job_no": "This job card no. already exists."})
        item_code = payload["item_code"].strip().upper()
        qty = _num(payload["qty"])
        counter = list(InvNo.objects.values_list("next_jc_no", flat=True)[:1])
        JobCard.objects.create(
            job_no=job_no, div=DIV, job_date=job_date, item_code=item_code, qty=qty,
            received=Decimal("0"), received_qty=Decimal("0"), waste=Decimal("0"), close_flag="N",
            sub_assembly="N", supervisor=(payload.get("supervisor") or "").strip()[:4],
            start_date=_parse_date(payload.get("start_date")), time_taken=Decimal("0"),
            issue_flag="N", uname=username[:10],
        )
        components = list(BomComponent.objects.filter(item_code=item_code).values_list("part_code", "quantity"))
        lines = []
        for part_code, quantity in components:
            need = (quantity or Decimal("0")) * qty
            lines.append(JobLine(div=DIV, line_date=job_date, part_code=part_code, qty=need,
                                 status="S", job_no=job_no, item_code=item_code, batch_no=job_no,
                                 uname=username[:10]))
            Part.objects.filter(part_number=part_code).update(current_stock=F("current_stock") - need)
        if lines:
            JobLine.objects.bulk_create(lines)
        if counter is not None and job_no.isdigit():
            InvNo.objects.update(next_jc_no=max(int(counter[0] or 0) if counter else 0, int(job_no)))
    return {"job_no": job_no}


def save_modify(payload, username=""):
    with transaction.atomic(using="legacy"):
        job_no, job_date = _validate_header(payload, is_add=False)
        j = _first_value(JobCard.objects.select_for_update().filter(job_no=job_no))
        if not j:
            raise JobError("Job card not found.")
        if _clean(j.close_flag) == "Y":
            raise JobError("Job card already closed. Unable to modify.")
        if _clean(j.sub_assembly) == "Y":
            raise JobError("Sub-assembly job card. Unable to modify.")
        j.job_date = job_date
        j.supervisor = (payload.get("supervisor") or "").strip()[:4]
        j.start_date = _parse_date(payload.get("start_date"))
        j.uname = username[:10]
        j.save(update_fields=["job_date", "supervisor", "start_date", "uname"])
    return {"job_no": job_no}


def delete_job(job_no):
    with transaction.atomic(using="legacy"):
        j = _first_value(JobCard.objects.select_for_update().filter(job_no=job_no))
        if not j:
            raise JobError("Job card not found.")
        if _clean(j.close_flag) == "Y":
            raise JobError("Job card already closed. Unable to delete.")
        if _clean(j.sub_assembly) == "Y":
            raise JobError("Sub-assembly job card. Unable to delete.")
        issued = list(JobLine.objects.filter(job_no=job_no, status="S").values_list("part_code", "qty"))
        for part_code, qty_issued in issued:
            Part.objects.filter(part_number=part_code).update(current_stock=F("current_stock") + (qty_issued or Decimal("0")))
        with connections["legacy"].cursor() as cur:
            cur.execute("DELETE FROM imaster WHERE job_no = %s AND stts = 'S'", [job_no])
            cur.execute("DELETE FROM new_job WHERE job_no = %s", [job_no])
    return {"job_no": job_no}


def receive_job(job_no, qty, username=""):
    qty = _num(qty)
    if qty is None or qty <= 0:
        raise JobError("Receive qty must be greater than zero.", {"qty": "Enter a quantity above zero."})
    with transaction.atomic(using="legacy"):
        j = _first_value(JobCard.objects.select_for_update().filter(job_no=job_no))
        if not j:
            raise JobError("Job card not found.")
        if _clean(j.close_flag) == "Y":
            raise JobError("Job card already closed.")
        done = j.received_qty or Decimal("0")
        if done + qty > (j.qty or Decimal("0")):
            raise JobError("Received qty exceeds job qty.", {"qty": "Received qty can't exceed job qty."})
        j.received_qty = done + qty
        j.uname = username[:10]
        j.save(update_fields=["received_qty", "uname"])
        JobLine.objects.bulk_create([JobLine(div=DIV, line_date=date.today(), part_code=j.item_code, qty=qty,
                                             status="P", job_no=job_no, item_code=j.item_code, batch_no=job_no,
                                             uname=username[:10])])
        code = (j.item_code or "")[:4]
        if not StockBalance.objects.filter(item_code=code).update(stock=F("stock") + qty):
            StockBalance.objects.bulk_create([StockBalance(item_code=code, stock=qty)])
    return {"job_no": job_no}


def close_job(job_no, payload, username=""):
    with transaction.atomic(using="legacy"):
        j = _first_value(JobCard.objects.select_for_update().filter(job_no=job_no))
        if not j:
            raise JobError("Job card not found.")
        if _clean(j.close_flag) == "Y":
            raise JobError("Job card already closed.")
        if (j.received_qty or Decimal("0")) != (j.qty or Decimal("0")):
            raise JobError("Unable to close: received qty doesn't match job qty.")
        j.close_flag = "Y"
        j.close_date = _parse_date(payload.get("close_date")) or date.today()
        j.received = Decimal(str(payload.get("received") or "0")).quantize(Decimal("1"), ROUND_HALF_UP)
        j.waste = Decimal(str(payload.get("waste") or "0")).quantize(Decimal("1"), ROUND_HALF_UP)
        j.time_taken = Decimal(str(payload.get("time_taken") or "0")).quantize(Q2, ROUND_HALF_UP)
        j.uname = username[:10]
        j.save(update_fields=["close_flag", "close_date", "received", "waste", "time_taken", "uname"])
    return {"job_no": job_no}


def search_items(term, limit=15):
    term = (term or "").strip()
    qs = Item.objects.all()
    if term:
        qs = Item.objects.filter(item_code__istartswith=term) | Item.objects.filter(item_name_1__icontains=term)
    return [
        {"code": _clean(c), "name": _clean(n) or "", "unit": _clean(u) or ""}
        for c, n, u in qs.order_by("item_code").values_list("item_code", "item_name_1", "unit")[:limit]
    ]


def job_card_listing(start, end):
    """Legacy JOB CARD LIST: non-sub-assembly jobs dated start..end, oldest first."""
    from apps.items.models import Item as _Item
    from apps.supervisors.models import Supervisor

    jobs = JobCard.objects.filter(job_date__gte=start, job_date__lte=end).order_by("job_date", "job_no")
    items = {c: (n, u, t, r) for c, n, u, t, r in _Item.objects.values_list(
        "item_code", "item_name_1", "unit", "time_required", "invoice_rate")}
    supervisors = dict(Supervisor.objects.values_list("code", "name"))
    rows, total = [], Decimal("0")
    for j in jobs:
        if _clean(j.sub_assembly) == "Y":
            continue
        code = _clean(j.item_code) or ""
        name, unit, time_req, rate = items.get(code[:5], (None, None, None, None))
        qty = j.qty or Decimal("0")
        rate = rate or Decimal("0")
        amount = (qty * rate).quantize(Q2, ROUND_HALF_UP)
        total += amount
        closed = _clean(j.close_flag) == "Y"
        rows.append({
            "job_no": _clean(j.job_no), "date": j.job_date.isoformat() if j.job_date else "",
            "code": code, "item_name": _clean(name) or "", "unit": _clean(unit) or "",
            "qty": f"{qty:.2f}", "prod": f"{(j.received_qty or 0):.2f}",
            "time_reqd": f"{(qty * (time_req or 0) / 60):.2f}",
            "time_taken": f"{(j.time_taken or 0):.2f}",
            "closed": "Y" if closed else "N",
            "close_date": j.close_date.isoformat() if closed and j.close_date else "",
            "supervisor": _clean(supervisors.get((j.supervisor or "")[:4])) or "",
            "rate": f"{rate:.2f}", "amount": f"{amount:.2f}",
        })
    return {"rows": rows, "total": f"{total:.2f}"}


def search_supervisors(term, limit=15):
    from apps.supervisors.models import Supervisor

    term = (term or "").strip()
    qs = Supervisor.objects.all()
    if term:
        qs = Supervisor.objects.filter(code__istartswith=term) | Supervisor.objects.filter(name__icontains=term)
    return [{"code": _clean(c), "name": _clean(n) or ""}
            for c, n in qs.order_by("name").values_list("code", "name")[:limit]]


def job_card_supervisor_listing(start, end, supervisor_code):
    """Legacy supervisor-wise JOB CARD LIST: non-sub jobs of one supervisor dated start..end."""
    from apps.items.models import Item as _Item
    from apps.supervisors.models import Supervisor

    jobs = JobCard.objects.filter(job_date__gte=start, job_date__lte=end,
                                  supervisor=supervisor_code).order_by("job_date", "job_no")
    items = {c: (n, u, r) for c, n, u, r in _Item.objects.values_list("item_code", "item_name_1", "unit", "rate")}
    supervisor = _first_value(Supervisor.objects.filter(code=supervisor_code))
    rows, total = [], Decimal("0")
    for j in jobs:
        if _clean(j.sub_assembly) == "Y":
            continue
        code = _clean(j.item_code) or ""
        name, unit, rate = items.get(code[:4], (None, None, None))
        qty = j.qty or Decimal("0")
        rate = rate or Decimal("0")
        amount = (qty * rate).quantize(Q2, ROUND_HALF_UP)
        total += amount
        closed = _clean(j.close_flag) == "Y"
        rows.append({
            "job_no": _clean(j.job_no), "date": j.job_date.isoformat() if j.job_date else "",
            "code": code, "item_name": _clean(name) or "", "unit": _clean(unit) or "",
            "qty": f"{qty:.2f}", "prod": f"{(j.received or 0):.2f}",
            "wastage": f"{(j.waste or 0):.2f}",
            "closed": "Y" if closed else "N",
            "close_date": j.close_date.isoformat() if closed and j.close_date else "",
            "supervisor": _clean(supervisor.name) if supervisor else "",
            "rate": f"{rate:.2f}", "amount": f"{amount:.2f}",
        })
    return {"rows": rows, "total": f"{total:.2f}"}


def short_list(item_code, qty, with_rate):
    """Legacy SHORT-LIST: BOM components of one product for a quantity, with stock and shortage."""
    from apps.parts.models import Part as _Part

    item = _first_value(Item.objects.filter(item_code=item_code))
    if not item:
        return None
    parts = {p: (d, r, s, u) for p, d, r, s, u in _Part.objects.values_list(
        "part_number", "description_1", "purchase_rate", "current_stock", "unit")}
    rows = []
    for part_code, bom_qty in BomComponent.objects.filter(item_code=item_code).values_list("part_code", "quantity"):
        desc, rate, stock, unit = parts.get(part_code, (None, None, None, None))
        reqd = (bom_qty or Decimal("0")) * qty
        stock = stock or Decimal("0")
        short = stock - reqd
        rows.append({
            "code": _clean(part_code), "name": _clean(desc) or "", "unit": _clean(unit) or "",
            "rate": f"{(rate or 0):.2f}" if with_rate else "",
            "stock": f"{stock:.0f}", "reqd": f"{reqd:.0f}",
            "shortage": f"{short:.0f}" if short <= 0 else "",
        })
    return {"item_code": _clean(item.item_code), "item_name": _clean(item.item_name_1) or "",
            "qty": f"{qty:.0f}", "with_rate": with_rate, "rows": rows}


def _open_job(job_no, item_code):
    job = _first_value(JobCard.objects.filter(job_no=job_no))
    if not job:
        raise JobError("Job card not found.", {"job_no": "Job card not found."})
    if _clean(job.item_code) != item_code:
        raise JobError("Job card is for a different product.", {"job_no": "Job card is for a different product."})
    if _clean(job.close_flag) == "Y":
        raise JobError("Job card already closed.", {"job_no": "Job card already closed."})
    if _clean(job.sub_assembly) == "Y":
        raise JobError("Sub-assembly job card.", {"job_no": "Sub-assembly job card."})
    return job


def product_issue_list(start, end, search=""):
    lines = JobLine.objects.filter(status="S", line_date__gte=start, line_date__lte=end).exclude(
        serial_no__isnull=True).exclude(serial_no="").values("serial_no", "line_date", "item_code", "job_no")
    names = dict(Item.objects.values_list("item_code", "item_name_1"))
    term = (search or "").strip().lower()
    seen = {}
    for l in lines:
        seen.setdefault(_clean(l["serial_no"]), l)
    rows = []
    for serial, l in seen.items():
        name = _clean(names.get(_clean(l["item_code"]))) or ""
        if term and term not in serial.lower() and term not in name.lower():
            continue
        rows.append({"key": serial, "serial_no": serial,
                     "date": l["line_date"].isoformat() if l["line_date"] else "",
                     "item_code": _clean(l["item_code"]), "item_name": name[:30], "job_no": _clean(l["job_no"])})
    rows.sort(key=lambda r: (r["date"], r["serial_no"]), reverse=True)
    return rows


def product_issue_detail(serial):
    lines = list(JobLine.objects.filter(status="S", serial_no=serial).values(
        "line_date", "item_code", "job_no", "part_code", "qty"))
    if not lines:
        return None
    head = lines[0]
    names = dict(Part.objects.values_list("part_number", "description_1"))
    item = _first_value(Item.objects.filter(item_code=head["item_code"]))
    return {
        "serial_no": _clean(serial),
        "date": head["line_date"].isoformat() if head["line_date"] else "",
        "item_code": _clean(head["item_code"]),
        "item_name": _clean(item.item_name_1) if item else "",
        "job_no": _clean(head["job_no"]),
        "components": [{"part_code": _clean(l["part_code"]), "part_name": _clean(names.get(l["part_code"])) or "",
                        "qty": f"{(l['qty'] or 0):.3f}"} for l in lines],
    }


def product_issue_open_jobs(item_code):
    rows = []
    for j in JobCard.objects.filter(item_code=item_code).order_by("job_no"):
        if _clean(j.close_flag) == "Y" or _clean(j.sub_assembly) == "Y":
            continue
        rows.append({"job_no": _clean(j.job_no), "date": j.job_date.isoformat() if j.job_date else "",
                     "qty": f"{(j.qty or 0):.0f}"})
    return rows


def product_issue_preview(item_code, job_no):
    job = _open_job(job_no, item_code)
    qty = job.qty or Decimal("0")
    names = dict(Part.objects.values_list("part_number", "description_1"))
    return {"job_no": _clean(job.job_no), "qty": f"{qty:.0f}", "components": [
        {"part_code": _clean(p), "part_name": _clean(names.get(p)) or "",
         "qty": f"{((q or Decimal('0')) * qty):.3f}"}
        for p, q in BomComponent.objects.filter(item_code=item_code).values_list("part_code", "quantity")]}


def _restore_serial(serial):
    for part_code, qty in list(JobLine.objects.filter(status="S", serial_no=serial).values_list("part_code", "qty")):
        Part.objects.filter(part_number=part_code).update(
            stock_balance=Coalesce("stock_balance", Value(0)) + (qty or Decimal("0")))
    with connections["legacy"].cursor() as cur:
        cur.execute("DELETE FROM imaster WHERE jo_no = %s AND stts = 'S'", [serial])


def _issue_serial(serial, item_code, job_no, issue_date, username):
    job = _open_job(job_no, item_code)
    qty = job.qty or Decimal("0")
    lines = []
    for part_code, q in BomComponent.objects.filter(item_code=item_code).values_list("part_code", "quantity"):
        need = (q or Decimal("0")) * qty
        lines.append(JobLine(div=DIV, line_date=issue_date, part_code=part_code, qty=need, status="S",
                             serial_no=serial, job_no=job_no, item_code=item_code, uname=username[:10]))
        Part.objects.filter(part_number=part_code).update(stock_balance=Coalesce("stock_balance", Value(0)) - need)
    if lines:
        JobLine.objects.bulk_create(lines)


def product_issue_save(payload, mode, username=""):
    serial = (payload.get("serial_no") or "").strip()
    item_code = (payload.get("item_code") or "").strip().upper()
    job_no = (payload.get("job_no") or "").strip()
    issue_date = _parse_date(payload.get("date"))
    errors = {}
    if not serial:
        errors["serial_no"] = "Serial no. is empty."
    elif len(serial) > 9:
        errors["serial_no"] = "Serial no. is too long."
    if not issue_date:
        errors["date"] = "Serial date is empty."
    if not item_code:
        errors["item_code"] = "Select an item."
    if not job_no:
        errors["job_no"] = "Select a job card."
    if errors:
        raise JobError("Fix the highlighted fields.", errors)
    with transaction.atomic(using="legacy"):
        exists = JobLine.objects.filter(status="S", serial_no=serial).exists()
        if mode == "add" and exists:
            raise JobError("Serial No. already exists.", {"serial_no": "Serial No. already exists."})
        if mode == "modify":
            if not exists:
                raise JobError("Serial No. not found.", {"serial_no": "Serial No. not found."})
            _restore_serial(serial)
        _issue_serial(serial, item_code, job_no, issue_date, username)
    return {"serial_no": serial}


def product_issue_delete(serial):
    with transaction.atomic(using="legacy"):
        if not JobLine.objects.filter(status="S", serial_no=serial).exists():
            raise JobError("Serial No. not found.")
        _restore_serial(serial)
    return {"serial_no": serial}
