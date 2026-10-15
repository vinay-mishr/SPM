"""Stock > Production Schedule (New) > Based upon Inventory (VFP production schedule)."""
from decimal import Decimal, ROUND_HALF_UP

from django.db import connections


def _d(value):
    return Decimal(str(value or 0))


def _round(value):
    return Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _rows(sql, params=None):
    with connections["legacy"].cursor() as cur:
        cur.execute(sql, params or [])
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def production_schedule(start, end, tdays):
    mavg = max((end - start).days, 1)
    items = _rows("SELECT i_code, i_name, op_bal, rate, pre_bal, time_reqd FROM item ORDER BY i_code")
    before, period = {}, {}
    for r in _rows("SELECT i_code, stts, qty, date FROM i_master WHERE stts IN ('P','S','I','M') AND date <= %s", [end]):
        code = (r["i_code"] or "").strip()
        qty = _d(r["qty"])
        if r["date"] < start:
            before[code] = before.get(code, Decimal("0")) + (qty if r["stts"] == "P" else -qty)
        else:
            bucket = period.setdefault(code, {"P": Decimal("0"), "S": Decimal("0"), "I": Decimal("0"), "M": Decimal("0")})
            bucket[r["stts"]] += qty
    pending = {}
    for r in _rows("SELECT i_code, stock, issue FROM order1 WHERE COALESCE(adj, '') <> 'Y'"):
        code = (r["i_code"] or "").strip()
        pending[code] = pending.get(code, Decimal("0")) + _d(r["stock"]) - _d(r["issue"])
    in_process = {}
    for r in _rows("SELECT i_code, qty FROM new_job WHERE COALESCE([close], '') <> 'Y'"):
        code = (r["i_code"] or "").strip()
        in_process[code] = in_process.get(code, Decimal("0")) + _d(r["qty"])

    tdays = Decimal(tdays)
    rows, total_hrs = [], Decimal("0")
    for it in items:
        code = (it["i_code"] or "").strip()
        name = (it["i_name"] or "").strip()
        pend = pending.get(code, Decimal("0"))
        mopbal = _d(it["op_bal"]) + before.get(code, Decimal("0"))
        p = period.get(code, {"P": Decimal("0"), "S": Decimal("0"), "I": Decimal("0"), "M": Decimal("0")})
        if mopbal == 0 and p["P"] == 0 and p["S"] == 0 and p["I"] == 0 and p["M"] == 0:
            if pend > 0:
                rows.append({"code": code, "name": name, "pending": f"{pend:.2f}", "pending_only": True})
            continue
        gip = in_process.get(code, Decimal("0"))
        balance = mopbal + p["P"] - p["S"] - p["I"] - p["M"]
        sale = p["S"] + p["I"] + p["M"]
        sale_avg = _round(sale / mavg * 30)
        pre = _d(it["pre_bal"])
        cur_sale_days = sale_avg / 30 * tdays
        last_year_days = pre / 30 * tdays
        if cur_sale_days > last_year_days:
            required = _round(pend + cur_sale_days - gip - balance)
        else:
            required = _round(pend + last_year_days - gip - balance)
        if required <= 0:
            continue
        time_req = _d(it["time_reqd"])
        man_hrs = Decimal("0") if time_req == 0 else (required * time_req).quantize(Decimal("0.01"), ROUND_HALF_UP) * 100 / 60
        total_hrs += man_hrs
        rows.append({
            "code": code, "name": name, "pending": f"{pend:.2f}", "pending_only": False,
            "cur_sale": f"{cur_sale_days:.2f}", "last_sale": f"{last_year_days:.2f}",
            "in_process": f"{gip:.2f}", "closing": f"{balance:.2f}", "required": f"{required:.2f}",
            "man_hrs": f"{man_hrs:.2f}", "time_per_unit": f"{time_req:.2f}",
        })
    for n, r in enumerate(rows, start=1):
        r["sno"] = n
    return {"rows": rows, "total_man_hrs": f"{total_hrs:.2f}"}


def production_pending(start, end):
    from apps.parts.models import Part

    items = _rows("SELECT i_code, i_name, op_bal, rate, time_reqd FROM item ORDER BY i_code")
    before, period = {}, {}
    for r in _rows("SELECT i_code, stts, qty, date FROM i_master WHERE stts IN ('P','S','I','M') AND date <= %s", [end]):
        code = (r["i_code"] or "").strip()
        qty = _d(r["qty"])
        if r["date"] < start:
            before[code] = before.get(code, Decimal("0")) + (qty if r["stts"] == "P" else -qty)
        else:
            bucket = period.setdefault(code, {"P": Decimal("0"), "S": Decimal("0"), "I": Decimal("0"), "M": Decimal("0")})
            bucket[r["stts"]] += qty
    pending = {}
    for r in _rows("SELECT i_code, stock, issue FROM order1 WHERE COALESCE(adj, '') <> 'Y' "
                   "AND DATEADD(day, COALESCE(del_days, 0), [date]) <= %s", [end]):
        code = (r["i_code"] or "").strip()
        pending[code] = pending.get(code, Decimal("0")) + _d(r["stock"]) - _d(r["issue"])
    in_process = {}
    for r in _rows("SELECT i_code, qty FROM new_job WHERE COALESCE([close], '') <> 'Y'"):
        code = (r["i_code"] or "").strip()
        in_process[code] = in_process.get(code, Decimal("0")) + _d(r["qty"])
    current = {p.part_number.strip(): _d(p.current_stock) for p in Part.objects.all() if p.part_number}

    rows, total_hrs = [], Decimal("0")
    for it in items:
        code = (it["i_code"] or "").strip()
        name = (it["i_name"] or "").strip()
        pend = pending.get(code, Decimal("0"))
        mopbal = _d(it["op_bal"]) + before.get(code, Decimal("0"))
        p = period.get(code, {"P": Decimal("0"), "S": Decimal("0"), "I": Decimal("0"), "M": Decimal("0")})
        if mopbal == 0 and p["P"] == 0 and p["S"] == 0 and p["I"] == 0 and p["M"] == 0:
            if pend > 0:
                rows.append({"code": code, "name": name, "pending": f"{pend:.2f}", "pending_only": True})
            continue
        gip = in_process.get(code, Decimal("0"))
        balance = current.get(code, Decimal("0"))
        required = pend - balance - gip
        if required <= 0:
            continue
        time_req = _d(it["time_reqd"])
        man_hrs = Decimal("0") if time_req == 0 else (required.quantize(Decimal("0.01"), ROUND_HALF_UP) * time_req) * 100 / 60
        total_hrs += man_hrs
        rows.append({
            "code": code, "name": name, "pending": f"{pend:.2f}", "pending_only": False,
            "in_process": f"{gip:.2f}", "closing": f"{balance:.2f}", "required": f"{required:.2f}",
            "man_hrs": f"{man_hrs:.2f}", "time_per_unit": f"{time_req:.2f}",
        })
    for n, r in enumerate(rows, start=1):
        r["sno"] = n
    return {"rows": rows, "total_man_hrs": f"{total_hrs:.2f}"}
