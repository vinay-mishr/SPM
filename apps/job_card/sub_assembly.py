"""Job Card (Sub Assembly) entry, from the VFP JOB ENTRY(SUB-ASSEMBLY) form.

Numbering: inv_no.ws_jc_no, job no = division + number.
ADD: header (new_job, sub='Y'); components from the sub-assembly BOM (conms) issued as S lines,
     part current stock reduced by BOM qty x job qty.
MODIFY: header only (date, product, qty), as the VFP form does.
DELETE: restores the issued stock, removes the S lines and the header, steps the counter back.
CLOSE: needs the issue entry done (iss='Y'); sets close date, produced qty, finish rejection;
       adds the produced qty to the product's stock and writes a P line.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.db import connections, transaction
from django.db.models.functions import Coalesce
from django.db.models import Value

from apps.bom.models import BomSaComponent
from apps.parts.models import Part

from .models import JobCard, JobLine

DIV = "SP"


class SubAssemblyError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def _d(value):
    try:
        return Decimal(str(value or "0").strip() or "0")
    except InvalidOperation:
        return None


def _date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _ws_counter():
    cur = connections["legacy"].cursor()
    cur.execute("SELECT ws_jc_no FROM inv_no")
    row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def _set_ws_counter(value):
    cur = connections["legacy"].cursor()
    cur.execute("UPDATE inv_no SET ws_jc_no = %s", [value])


def next_no():
    return _ws_counter() + 1


def _job_no(number):
    return f"{DIV}{number}"


def list_entries(start, end, search=""):
    qs = JobCard.objects.filter(sub_assembly="Y", job_date__gte=start, job_date__lte=end).values(
        "job_no", "job_date", "item_code", "qty", "received", "close_flag", "issue_flag")
    names = dict(Part.objects.values_list("part_number", "description_1"))
    term = (search or "").strip().lower()
    rows = []
    for h in qs:
        job_no = (h["job_no"] or "").strip()
        number = job_no[len(DIV):] if job_no.startswith(DIV) else job_no
        name = (names.get((h["item_code"] or "").strip()) or "").strip()
        if term and term not in job_no.lower() and term not in name.lower():
            continue
        rows.append({
            "number": number, "job_no": job_no,
            "job_date": h["job_date"].isoformat() if h["job_date"] else "",
            "item_code": (h["item_code"] or "").strip(), "item_name": name,
            "qty": f"{(h['qty'] or 0):.3f}", "produced": f"{(h['received'] or 0):.3f}",
            "closed": (h["close_flag"] or "").strip() == "Y",
            "issued": (h["issue_flag"] or "").strip() == "Y",
        })
    rows.sort(key=lambda r: (r["job_date"], int(r["number"]) if r["number"].isdigit() else 0), reverse=True)
    return rows


def load(number):
    job_no = _job_no(number)
    head = JobCard.objects.filter(job_no=job_no, sub_assembly="Y").values(
        "job_no", "job_date", "item_code", "qty", "received", "waste", "close_flag", "close_date",
        "issue_flag")[:1]
    rows = list(head)
    if not rows:
        return None
    h = rows[0]
    part = Part.objects.filter(part_number=(h["item_code"] or "").strip()).values_list("description_1", flat=True)[:1]
    return {
        "number": str(number), "job_no": h["job_no"],
        "job_date": h["job_date"].isoformat() if h["job_date"] else "",
        "item_code": (h["item_code"] or "").strip(),
        "item_name": ((list(part)[0] if part else "") or "").strip(),
        "qty": f"{(h['qty'] or 0):.3f}",
        "produced": f"{(h['received'] or 0):.3f}",
        "finish_rejection": f"{(h['waste'] or 0):.3f}",
        "close_date": h["close_date"].isoformat() if h["close_date"] else "",
        "closed": (h["close_flag"] or "").strip() == "Y",
        "issued": (h["issue_flag"] or "").strip() == "Y",
    }


def _product(code):
    code = (code or "").strip().upper()
    if not code or not Part.objects.filter(part_number=code).exists():
        raise SubAssemblyError("Product not found in the Part Master.", {"item_code": "Product not found."})
    return code


def add(payload, username=""):
    qty = _d(payload.get("qty"))
    job_date = _date(payload.get("job_date"))
    errors = {}
    if not job_date:
        errors["job_date"] = "Enter the job date."
    if qty is None or qty <= 0:
        errors["qty"] = "Job qty must be greater than zero."
    code = _product(payload.get("item_code")) if not errors else None
    if errors:
        raise SubAssemblyError("Fix the highlighted fields.", errors)
    with transaction.atomic(using="legacy"):
        number = next_no()
        job_no = _job_no(number)
        if JobCard.objects.filter(job_no=job_no).exists():
            raise SubAssemblyError("Job no. already exists.")
        JobCard.objects.create(job_no=job_no, div=DIV, sub_assembly="Y", job_date=job_date, item_code=code,
                               qty=qty, received=Decimal("0"), received_qty=Decimal("0"), waste=Decimal("0"),
                               close_flag="N", time_taken=Decimal("0"), uname=username[:10])
        for comp in BomSaComponent.objects.filter(parent_part_code=code):
            need = (comp.quantity or Decimal("0")) * qty
            JobLine.objects.create(div=DIV, line_date=job_date, part_code=comp.component_part_code, qty=need,
                                   status="S", job_no=job_no, item_code=code, batch_no=job_no, uname=username[:10])
            Part.objects.filter(part_number=comp.component_part_code).update(
                current_stock=Coalesce("current_stock", Value(0)) - need)
        _set_ws_counter(number)
    return {"job_no": job_no}


def modify(number, payload, username=""):
    job_no = _job_no(number)
    with transaction.atomic(using="legacy"):
        job = JobCard.objects.select_for_update().filter(job_no=job_no, sub_assembly="Y").first()
        if not job:
            raise SubAssemblyError("Job no. not found.")
        if job.close_flag == "Y":
            raise SubAssemblyError("Job Card Already Closed.")
        job_date = _date(payload.get("job_date"))
        if job_date:
            job.job_date = job_date
        qty = _d(payload.get("qty"))
        if qty is not None and qty > 0:
            job.qty = qty
        job.uname = username[:10]
        job.save(update_fields=["job_date", "qty", "uname"])
    return {"job_no": job_no}


def delete(number):
    job_no = _job_no(number)
    with transaction.atomic(using="legacy"):
        job = JobCard.objects.select_for_update().filter(job_no=job_no, sub_assembly="Y").first()
        if not job:
            raise SubAssemblyError("Job no. not found.")
        if job.close_flag == "Y":
            raise SubAssemblyError("Job Card Already Closed.")
        for line in JobLine.objects.filter(job_no=job_no, status="S").values("part_code", "qty"):
            Part.objects.filter(part_number=line["part_code"]).update(
                current_stock=Coalesce("current_stock", Value(0)) + (line["qty"] or Decimal("0")))
        with connections["legacy"].cursor() as cur:
            cur.execute("DELETE FROM imaster WHERE job_no = %s AND stts = 'S'", [job_no])
        JobCard.objects.filter(job_no=job_no).delete()
        if _ws_counter() > number - 1:
            _set_ws_counter(number - 1)
    return {"job_no": job_no}


def close(number, payload, username=""):
    job_no = _job_no(number)
    produced = _d(payload.get("produced"))
    rejection = _d(payload.get("finish_rejection")) or Decimal("0")
    close_date = _date(payload.get("close_date")) or date.today()
    if produced is None or produced <= 0:
        raise SubAssemblyError("Produced qty must be greater than zero.", {"produced": "Enter the produced qty."})
    with transaction.atomic(using="legacy"):
        job = JobCard.objects.select_for_update().filter(job_no=job_no, sub_assembly="Y").first()
        if not job:
            raise SubAssemblyError("Job no. not found.")
        if job.close_flag == "Y":
            raise SubAssemblyError("Job Card Already Closed.")
        if (job.issue_flag or "").strip() != "Y":
            raise SubAssemblyError("UNABLE TO CONFIRM... ISSUE ENTRY NOT ENTERED.")
        job.close_date = close_date
        job.received = produced
        job.waste = rejection
        job.close_flag = "Y"
        job.uname = username[:10]
        job.save(update_fields=["close_date", "received", "waste", "close_flag", "uname"])
        JobLine.objects.create(div=DIV, line_date=close_date, part_code=job.item_code, qty=produced, status="P",
                               job_no=job_no, item_code=job.item_code, batch_no=job_no, uname=username[:10])
        Part.objects.filter(part_number=job.item_code).update(
            stock_balance=Coalesce("stock_balance", Value(0)) + produced)
    return {"job_no": job_no}
