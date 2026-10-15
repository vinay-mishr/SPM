"""Creditor Outstanding > Payment Entry -- settles creditor bills and posts JV / CV vouchers.

Ported from the VFP payment routine (aa.prg / account.prg codes):
  PSCCODE=S002 (sundry creditors), PCASHCODE=C001 (cash), PCDCODE=R001 (rebate & discount).
  Interest 1008 and bank charges B001 are literal codes in the VFP routine.
"""
from decimal import Decimal, ROUND_HALF_UP

from django.db import connections, transaction
from django.db.models import F, Value
from django.db.models.functions import Coalesce

from apps.gl.models import Ledger
from apps.parties.models import Party

from .models import CreditorBill, LedgerVoucher, PaymentDetail, VoucherCounter

PSCCODE = "S002"
PCASHCODE = "C001"
PCDCODE = "R001"
INTEREST_CODE = "1008"
BANK_CHARGE_CODE = "B001"
BANK_MODES = {"NE", "CH"}
Q2 = Decimal("0.01")


class PaymentError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def _d(value):
    return Decimal(str(value or 0))


def balance_of(b):
    return _d(b["amount"]) - _d(b["pmt_rcd"]) - _d(b["c_dis"]) + _d(b["int_amt"]) - _d(b["dr_amt"]) - _d(b["tds_amt"])


def pending_bills(party_code):
    rows = []
    qs = CreditorBill.objects.filter(p_code=party_code).exclude(pmt_mad="Y").order_by("inv_dt").values(
        "inv_no", "inv_dt", "amount", "dr_amt", "tds_amt", "pmt_rcd", "c_dis", "int_amt", "div")
    for b in qs:
        bal = balance_of(b)
        if bal <= 0:
            continue
        rows.append({
            "div": (b["div"] or "").strip(), "bill_no": (b["inv_no"] or "").strip(),
            "bill_date": b["inv_dt"].isoformat() if b["inv_dt"] else "",
            "bill_amount": f"{_d(b['amount']) - _d(b['tds_amt']):.2f}", "balance": f"{bal:.2f}",
        })
    return rows


def _settle_line(party_code, line, pay_date, chq_no, username):
    bill_no = line["bill_no"]
    bill_date = _parse(line.get("bill_date"))
    if not bill_date:
        raise PaymentError(f"Bill {bill_no}: bill date missing.")
    adj = _d(line["adjusted"])
    cdis = _d(line["cash_dis"])
    intr = _d(line["interest"])
    current = _first_bill(party_code, bill_no, bill_date)
    if not current:
        raise PaymentError(f"Bill {bill_no} dated {bill_date:%d/%m/%Y} not found.")
    outstanding = balance_of(current)
    if adj + cdis - intr > outstanding:
        raise PaymentError(f"Bill {bill_no}: amount {adj:.2f} exceeds its balance {outstanding:.2f}.",
                           {"lines": f"Bill {bill_no} balance is {outstanding:.2f}."})
    pmt_rcd = _d(current["pmt_rcd"]) + adj
    c_dis = _d(current["c_dis"]) + cdis
    int_amt = _d(current["int_amt"]) + intr
    remaining = balance_of({**current, "pmt_rcd": pmt_rcd, "c_dis": c_dis, "int_amt": int_amt})
    CreditorBill.objects.filter(p_code=party_code, inv_no=bill_no, inv_dt=bill_date).update(
        pmt_rcd=pmt_rcd, c_dis=c_dis, int_amt=int_amt, nar=chq_no, uname=username[:10],
        pmt_mad="Y" if remaining <= 0 else "N")
    return PaymentDetail(div=line["div"][:2], bill_no=bill_no, b_date=line["bill_date"], b_amt=_d(line["bill_amount"]),
                         p_code=party_code, amount=adj, c_dis=cdis, int_amt=intr, nar=chq_no,
                         date=pay_date, remk="", uname=username[:10])


def _first_bill(party_code, bill_no, bill_date):
    rows = list(CreditorBill.objects.filter(p_code=party_code, inv_no=bill_no, inv_dt=bill_date).values(
        "amount", "dr_amt", "tds_amt", "pmt_rcd", "c_dis", "int_amt", "pmt_mad")[:1])
    return rows[0] if rows else None


def _next_voucher_no(mtype, pay_date):
    field = "jvvno" if mtype == "JV" else "cvvno"
    VoucherCounter.objects.filter(date=pay_date).update(**{field: Coalesce(field, Value(0)) + 1})
    row = list(VoucherCounter.objects.filter(date=pay_date).values_list(field, flat=True)[:1])
    if row:
        return int(row[0])
    VoucherCounter.objects.bulk_create([VoucherCounter(date=pay_date, **{field: 1})])
    return 1


def _post(party_code, party_group, mtype, doc, pay_date, mode, bank_code, amount_total, amount_paid,
          bank_charges, cash_dis_total, interest_total, chq_no, remarks, username):
    name = Party.objects.filter(party_code=party_code).values_list("name", flat=True)[:1]
    party_name = (list(name)[0] if name else "") or ""
    rows = []

    def add(tcode, tccode, dbcr, amount, nar1, nar2=""):
        rows.append(LedgerVoucher(ttype=mtype, tdoc=doc, tdate=pay_date, tcode=tcode, tccode=tccode, tdbcr=dbcr,
                                  tnar1=nar1[:40], tnar2=nar2[:40], tamt=amount, nar=chq_no, p_code=party_code,
                                  uname=username[:10]))

    if mode in BANK_MODES:
        add(bank_code, "", "C", amount_total, f"Chq. No {chq_no}", party_name + remarks)
        if cash_dis_total:
            add(party_group, party_code, "D", cash_dis_total, f"Cash Dis. No {chq_no}", remarks)
        if bank_charges:
            add(BANK_CHARGE_CODE, "", "D", bank_charges, "Bank charges", remarks)
        add(PSCCODE, party_code, "D", amount_paid, f"Chq. No {chq_no}", remarks)
    else:
        add(PCASHCODE, "", "C", amount_total, "Cash Paid", remarks)
        add(PSCCODE, party_code, "D", amount_paid, "Cash Paid", remarks)
    if cash_dis_total:
        add(PCDCODE, "", "C", cash_dis_total, "Rebate & Discount", remarks)
    if interest_total:
        add(INTEREST_CODE, "", "D", interest_total, "Interest Charges", remarks)
    LedgerVoucher.objects.bulk_create(rows)


def save_payment(payload, username=""):
    errors = {}
    party_code = (payload.get("party_code") or "").strip().upper()
    party = Party.objects.filter(party_code=party_code).values_list("group_code", flat=True)[:1]
    if not party:
        errors["party_code"] = "Select a vendor."
    chq_no = (payload.get("chq_no") or "").strip()
    if not chq_no:
        errors["chq_no"] = "Enter the cheque / NEFT / receipt no."
    mode = (payload.get("mode") or "").strip().upper()
    if mode not in BANK_MODES | {"CA"}:
        errors["mode"] = "Choose NE, CH or CA."
    bank_code = (payload.get("bank_code") or "").strip()
    if mode in BANK_MODES and not Ledger.objects.filter(ledger_code=bank_code).exists():
        errors["bank_code"] = "Select the bank."
    pay_date = _parse(payload.get("date"))
    if not pay_date:
        errors["date"] = "Enter the payment date."
    amount_paid = _d(payload.get("amount_paid"))
    if amount_paid <= 0:
        errors["amount_paid"] = "Enter the amount paid."
    bank_charges = _d(payload.get("bank_charges"))
    lines = [l for l in (payload.get("lines") or []) if _d(l.get("adjusted")) != 0]
    if not lines:
        errors["lines"] = "Add at least one bill."
    if errors:
        raise PaymentError("Fix the highlighted fields.", errors)
    group_code = party[0] or PSCCODE
    cash_dis_total = sum((_d(l.get("cash_dis")) for l in lines), Decimal("0"))
    interest_total = sum((_d(l.get("interest")) for l in lines), Decimal("0"))
    adjusted_total = sum((_d(l.get("adjusted")) for l in lines), Decimal("0"))
    amount_total = (amount_paid + bank_charges).quantize(Q2, ROUND_HALF_UP)
    mtype = "JV" if mode in BANK_MODES else "CV"
    remarks = (payload.get("remarks") or "").strip()[:40]

    with transaction.atomic(using="legacy"):
        if PaymentDetail.objects.filter(p_code=party_code, nar=chq_no).exists():
            raise PaymentError("Payment no. already exists.", {"chq_no": "This payment no. already exists."})
        doc = _next_voucher_no(mtype, pay_date)
        details = []
        for line in lines:
            details.append(_settle_line(party_code, {**line, "div": line.get("div") or ""}, pay_date, chq_no, username))
        PaymentDetail.objects.bulk_create(details)
        _post(party_code, group_code, mtype, doc, pay_date, mode, bank_code, amount_total, amount_paid,
              bank_charges, cash_dis_total, interest_total, chq_no, remarks, username)
    return {"chq_no": chq_no, "voucher": f"{mtype} {doc}", "adjusted": f"{adjusted_total:.2f}"}


def delete_payment(party_code, chq_no):
    party_code = (party_code or "").strip().upper()
    lines = list(PaymentDetail.objects.filter(p_code=party_code, nar=chq_no).values(
        "bill_no", "b_date", "amount", "c_dis", "int_amt"))
    if not lines:
        raise PaymentError("Payment not found.")
    with transaction.atomic(using="legacy"):
        for line in lines:
            current = _first_bill(party_code, line["bill_no"], line["b_date"])
            if not current:
                continue
            CreditorBill.objects.filter(p_code=party_code, inv_no=line["bill_no"], inv_dt=line["b_date"]).update(
                pmt_rcd=_d(current["pmt_rcd"]) - _d(line["amount"]),
                c_dis=_d(current["c_dis"]) - _d(line["c_dis"]),
                int_amt=_d(current["int_amt"]) - _d(line["int_amt"]),
                pmt_mad="N")
        with connections["legacy"].cursor() as cur:
            cur.execute("DELETE FROM p_col WHERE p_code = %s AND nar = %s", [party_code, chq_no])
            cur.execute("DELETE FROM trans WHERE p_code = %s AND nar = %s", [party_code, chq_no])
    return {"chq_no": chq_no}


def _parse(value):
    from datetime import datetime
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def list_payments():
    rows = {}
    for p in PaymentDetail.objects.values("p_code", "nar", "date", "amount", "int_amt", "c_dis"):
        key = (p["p_code"] or "", p["nar"] or "")
        r = rows.setdefault(key, {"party_code": key[0], "chq_no": key[1], "date": p["date"],
                                  "amount": Decimal("0")})
        r["amount"] += _d(p["amount"])
    names = dict(Party.objects.values_list("party_code", "name"))
    out = [{"key": f"{r['party_code']}|{r['chq_no']}", "party_code": r["party_code"],
            "party_name": (names.get(r["party_code"]) or "").strip(), "chq_no": r["chq_no"],
            "date": r["date"].isoformat() if r["date"] else "", "amount": f"{r['amount']:.2f}"}
           for r in rows.values()]
    out.sort(key=lambda x: (x["date"], x["chq_no"]), reverse=True)
    return out


def get_payment(party_code, chq_no):
    lines = list(PaymentDetail.objects.filter(p_code=party_code, nar=chq_no).values(
        "div", "bill_no", "b_date", "b_amt", "amount", "c_dis", "int_amt", "date"))
    if not lines:
        return None
    head = lines[0]
    cash_mode = LedgerVoucher.objects.filter(p_code=party_code, nar=chq_no, tnar1="Cash Paid").exists()
    bank = LedgerVoucher.objects.filter(p_code=party_code, nar=chq_no, tdbcr="C").values_list("tcode", flat=True)[:1]
    party = Party.objects.filter(party_code=party_code).values_list("name", flat=True)[:1]
    return {
        "party_code": party_code,
        "party_name": (list(party)[0] if party else "") or "",
        "chq_no": chq_no,
        "date": head["date"].isoformat() if head["date"] else "",
        "mode": "CA" if cash_mode else "NE",
        "bank_code": (list(bank)[0] if bank else "") or "",
        "amount_paid": f"{sum((_d(l['amount']) for l in lines), Decimal('0')):.2f}",
        "lines": [{"div": (l["div"] or "").strip(), "bill_no": (l["bill_no"] or "").strip(),
                   "bill_date": l["b_date"].isoformat() if l["b_date"] else "",
                   "bill_amount": f"{_d(l['b_amt']):.2f}", "balance": f"{_d(l['b_amt']):.2f}",
                   "cash_dis": f"{_d(l['c_dis']):.2f}", "interest": f"{_d(l['int_amt']):.2f}",
                   "adjusted": f"{_d(l['amount']):.2f}"} for l in lines],
    }
