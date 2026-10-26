"""
Bill of Material Master (Sub Assembly) logic (old software's ``conms`` table --
a separate physical table from ``con-mst``, which belongs only to the plain,
Item-wise Bill of Material Master screen further down this file). Each part
(part-mst) can have a set of component PARTS (also part-mst) with a quantity
each -- verified against a real reference screenshot and the live ``conms``
data: parent ABM01 "INFEED ASSY" has components ABM01_001 "FLAT", ABM01_002
"DRUM", etc., all real part-mst rows.
Because the real table has no key -- not even (parent_part_code,
component_part_code) is always unique -- a save always replaces *all*
component rows for one part in a single transaction, instead of updating
individual rows.
"""
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.db.models import Count, F

from apps.items.models import Item
from apps.parts.models import Part
from apps.parts.services import duplicate_part_numbers
from apps.parties.models import Party

from .models import BomComponent, BomSaComponent

PERMISSION = "bom.change_bom"
MAX_QTY = Decimal("9999999.99999")  # con-mst.qty is decimal(12, 5)


class BomError(Exception):
    """A save / delete that must be refused, with a message for the user."""

    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def writes_enabled():
    return "legacy" not in settings.DATABASES or settings.LEGACY_WRITES_ENABLED


def _db():
    return BomComponent.objects.db


def _sa_db():
    return BomSaComponent.objects.db


def _clean(value):
    return (value or "").strip() if isinstance(value, str) or value is None else value


def _part_descriptions(codes):
    return dict(Part.objects.filter(part_number__in=set(codes)).values_list("part_number", "description_1"))


def _part_units(codes):
    return dict(Part.objects.filter(part_number__in=set(codes)).values_list("part_number", "unit"))


def _item_names(codes):
    return dict(Item.objects.filter(item_code__in=set(codes)).values_list("item_code", "item_name_1"))


def _item_units(codes):
    return dict(Item.objects.filter(item_code__in=set(codes)).values_list("item_code", "unit"))


def list_parents():
    """One row per part that has a BOM defined, with its component count."""
    rows = list(
        BomSaComponent.objects.values(part_code=F("parent_part_code"))
        .annotate(component_count=Count("component_part_code"))
        .order_by("part_code")
    )
    names = _part_descriptions(r["part_code"] for r in rows)
    units = _part_units(r["part_code"] for r in rows)
    duplicates = duplicate_part_numbers()
    return [
        {
            "part_code": r["part_code"],
            "part_name": _clean(names.get(r["part_code"])),
            "unit": _clean(units.get(r["part_code"])),
            "component_count": r["component_count"],
            "is_duplicate": r["part_code"] in duplicates,
        }
        for r in rows
    ]


def search_parts(term, limit=3000, only_sub_assembly=False):
    """Part Master lookup by code or description (for the parent "Item Name" field).
    A blank term returns the first parts so the Help popup has something to show
    as soon as it opens, instead of "No matches". The limit is high enough to cover
    the whole Part Master table, so the Help popup can show and scroll through all
    of them rather than only the first few. Sorted alphabetically by description
    (case-insensitive), like the Part Master grid itself.
    ``only_sub_assembly`` restricts the list to parts flagged as a sub-assembly
    (for the parent "Item Name" field, which only makes sense for those)."""
    from django.db.models.functions import Lower

    term = (term or "").strip()
    duplicates = duplicate_part_numbers()
    if term:
        qs = Part.objects.filter(part_number__istartswith=term) | Part.objects.filter(description_1__icontains=term)
    else:
        qs = Part.objects.all()
    if only_sub_assembly:
        qs = qs.filter(sub_assembly="Y")
    qs = qs.annotate(name_lower=Lower("description_1"))
    return [
        {"code": c, "name": _clean(n), "unit": _clean(u), "material": _clean(m),
         "gst_percent": f"{g:.2f}" if g is not None else "", "is_duplicate": c in duplicates,
         "sub_assembly": "Y" if sa == "Y" else ""}
        for c, n, u, m, g, sa in qs.order_by("name_lower", "part_number").values_list(
            "part_number", "description_1", "unit", "material", "gst_percent", "sub_assembly"
        )[:limit]
    ]


def search_items(term, limit=3000):
    """Item Master lookup by code or name (for adding a component row).
    A blank term returns the first items so the Help popup has something to show
    as soon as it opens, instead of "No matches". Sorted alphabetically by name
    (case-insensitive), like the Item Master grid itself. The limit is high enough
    to cover the whole Item Master table, so the Help popup can show and scroll
    through all of them rather than only the first few."""
    from django.db.models.functions import Lower

    term = (term or "").strip()
    if term:
        qs = Item.objects.filter(item_code__istartswith=term) | Item.objects.filter(item_name_1__icontains=term)
    else:
        qs = Item.objects.all()
    qs = qs.annotate(name_lower=Lower("item_name_1"))
    return [
        {"code": c, "name": _clean(n), "unit": _clean(u)}
        for c, n, u in qs.order_by("name_lower", "item_code").values_list("item_code", "item_name_1", "unit")[:limit]
    ]


def get_components(part_code):
    """All BOM rows for one part, with component part descriptions filled in.
    Components are Part Master rows too (e.g. ABM01_001 "FLAT" under parent ABM01),
    not Item Master -- confirmed against a real reference screenshot and the live
    ``conms`` data."""
    rows = list(
        BomSaComponent.objects.filter(parent_part_code=part_code)
        .values("component_part_code", "quantity", "unit")
    )
    codes = [r["component_part_code"] for r in rows]
    names = _part_descriptions(codes)
    # The old conms table's own "unit" column is blank on some rows (never filled in
    # by the old software); fall back to the component's unit from Part Master.
    units = _part_units(codes)
    duplicates = duplicate_part_numbers()
    return [
        {
            "item_code": _clean(r["component_part_code"]),
            "item_name": _clean(names.get(r["component_part_code"])),
            "quantity": f"{(r['quantity'] or 0):.3f}",
            "unit": _clean(r["unit"]) or _clean(units.get(r["component_part_code"])),
            "is_duplicate": r["component_part_code"] in duplicates,
        }
        for r in rows
    ]


def parse_quantity(raw):
    text = str(raw if raw is not None else "").strip().replace(",", "")
    if text == "":
        raise ValueError("Enter the quantity.")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("Enter a number (for example 1.000).")
    if not value.is_finite() or value <= 0:
        raise ValueError("Quantity must be more than 0.")
    if value > MAX_QTY:
        raise ValueError("Quantity is too large.")
    return value.quantize(Decimal("0.00001"))


def _require_writes():
    if not writes_enabled():
        raise BomError("Saving to the SP_MACHINE database is switched off. Nothing was changed.")


def save(part_code, rows, username=""):
    """CONFIRM: replace every component row of ``part_code`` with the given set."""
    _require_writes()
    part_code = (part_code or "").strip().upper()
    if not part_code:
        raise BomError("Select the part this Bill of Material is for.", {"part_code": "Select a part."})
    if not Part.objects.filter(part_number=part_code).exists():
        raise BomError("That part was not found in Part Master.", {"part_code": "Select a part from Part Master."})
    if part_code in duplicate_part_numbers():
        raise BomError(
            "This part number exists more than once in the old data; its Bill of Material cannot be changed here.",
            {"part_code": "This part number is ambiguous in the old data."},
        )
    if not isinstance(rows, list) or not rows:
        raise BomError("Add at least one component.", {"": "Add at least one component."})

    item_codes = {(row or {}).get("item_code", "").strip().upper() for row in rows}
    item_codes.discard("")
    duplicates = duplicate_part_numbers()
    known_items = set(
        Part.objects.filter(part_number__in=item_codes).exclude(part_number__in=duplicates)
        .values_list("part_number", flat=True)
    )

    errors = {}
    cleaned = []
    seen = set()
    for index, row in enumerate(rows):
        item_code = str((row or {}).get("item_code", "")).strip().upper()
        key = f"row{index}"
        if not item_code:
            errors[key] = "Select a component."
            continue
        if item_code == part_code:
            errors[key] = "A part cannot be its own component."
            continue
        if item_code not in known_items:
            errors[key] = f"Part {item_code} was not found in Part Master (or is ambiguous in the old data)."
            continue
        if item_code in seen:
            errors[key] = f"Part {item_code} is listed more than once."
            continue
        try:
            quantity = parse_quantity((row or {}).get("quantity"))
        except ValueError as exc:
            errors[key] = str(exc)
            continue
        seen.add(item_code)
        cleaned.append({"item_code": item_code, "quantity": quantity, "unit": _clean((row or {}).get("unit"))[:3]})

    if errors:
        raise BomError("Some component rows are not valid.", errors)

    with transaction.atomic(using=_sa_db()):
        BomSaComponent.objects.filter(parent_part_code=part_code).delete()
        BomSaComponent.objects.bulk_create(
            BomSaComponent(
                parent_part_code=part_code, component_part_code=row["item_code"], quantity=row["quantity"],
                unit=row["unit"], uname=username[:10],
            )
            for row in cleaned
        )
    return len(cleaned)


def delete_bom(part_code):
    """Remove every component row for one part (the whole Bill of Material)."""
    _require_writes()
    part_code = (part_code or "").strip().upper()
    if part_code in duplicate_part_numbers():
        raise BomError(
            "This part number exists more than once in the old data; its Bill of Material cannot be deleted here."
        )
    deleted, _ = BomSaComponent.objects.filter(parent_part_code=part_code).delete()
    if not deleted:
        raise BomError("This part has no Bill of Material to delete.")


# --- Bill of Material Master (plain, Item-wise) ------------------------------------------
#
# Its own physical table, con-mst (BomComponent) -- separate from conms (BomSaComponent),
# which belongs to the Sub-Assembly screen above. Confirmed by querying the live legacy
# database: con-mst and conms are two distinct tables, so there is no data collision
# between these two screens after all. Here ITEM (item_code / "item" column) is the
# parent and PART (part_code / "icod" column) is the component.

def list_item_parents():
    """One row per item that has a BOM defined here, with its component count."""
    rows = list(
        BomComponent.objects.values("item_code").annotate(component_count=Count("part_code")).order_by("item_code")
    )
    names = _item_names(r["item_code"] for r in rows)
    units = _item_units(r["item_code"] for r in rows)
    return [
        {
            "item_code": r["item_code"],
            "item_name": _clean(names.get(r["item_code"])),
            "unit": _clean(units.get(r["item_code"])),
            "component_count": r["component_count"],
        }
        for r in rows
    ]


def get_components_for_item(item_code):
    """All BOM rows for one item, with part descriptions filled in."""
    rows = list(BomComponent.objects.filter(item_code=item_code).values("part_code", "quantity", "unit"))
    names = _part_descriptions(r["part_code"] for r in rows)
    duplicates = duplicate_part_numbers()
    return [
        {
            "part_code": _clean(r["part_code"]),
            "part_name": _clean(names.get(r["part_code"])),
            "quantity": f"{(r['quantity'] or 0):.3f}",
            "unit": _clean(r["unit"]),
            "is_duplicate": r["part_code"] in duplicates,
        }
        for r in rows
    ]


def save_for_item(item_code, rows, username=""):
    """CONFIRM: replace every component row of ``item_code`` with the given set."""
    _require_writes()
    item_code = (item_code or "").strip().upper()
    if not item_code:
        raise BomError("Select the item this Bill of Material is for.", {"item_code": "Select an item."})
    if not Item.objects.filter(item_code=item_code).exists():
        raise BomError("That item was not found in Item Master.", {"item_code": "Select an item from Item Master."})
    if not isinstance(rows, list) or not rows:
        raise BomError("Add at least one component.", {"": "Add at least one component."})

    part_codes = {(row or {}).get("part_code", "").strip().upper() for row in rows}
    part_codes.discard("")
    duplicates = duplicate_part_numbers()
    known_parts = set(
        Part.objects.filter(part_number__in=part_codes).exclude(part_number__in=duplicates)
        .values_list("part_number", flat=True)
    )

    errors = {}
    cleaned = []
    seen = set()
    for index, row in enumerate(rows):
        part_code = str((row or {}).get("part_code", "")).strip().upper()
        key = f"row{index}"
        if not part_code:
            errors[key] = "Select a component."
            continue
        if part_code not in known_parts:
            errors[key] = f"Part {part_code} was not found in Part Master (or is ambiguous in the old data)."
            continue
        if part_code in seen:
            errors[key] = f"Part {part_code} is listed more than once."
            continue
        try:
            quantity = parse_quantity((row or {}).get("quantity"))
        except ValueError as exc:
            errors[key] = str(exc)
            continue
        seen.add(part_code)
        cleaned.append({"part_code": part_code, "quantity": quantity, "unit": _clean((row or {}).get("unit"))[:3]})

    if errors:
        raise BomError("Some component rows are not valid.", errors)

    with transaction.atomic(using=_db()):
        BomComponent.objects.filter(item_code=item_code).delete()
        BomComponent.objects.bulk_create(
            BomComponent(
                item_code=item_code, part_code=row["part_code"], quantity=row["quantity"],
                unit=row["unit"], uname=username[:10],
            )
            for row in cleaned
        )
    return len(cleaned)


def delete_bom_for_item(item_code):
    """Remove every component row for one item (the whole Bill of Material)."""
    _require_writes()
    item_code = (item_code or "").strip().upper()
    deleted, _ = BomComponent.objects.filter(item_code=item_code).delete()
    if not deleted:
        raise BomError("This item has no Bill of Material to delete.")


# --- Consumption Master report -----------------------------------------------------------
#
# Read-only report over the same con-mst data as the plain Bill of Material Master screen
# above, matching the old VFP "CONSUMPTION MASTER" print/Excel (ITEMLIST.PRN): for one
# parent item, list every BOM component with its Part Master reference fields (material,
# wt/100, gauge, drawing no) and a computed Value = qty * Part.purchase_rate. One function
# feeds both the on-page table and the Excel export, so they can never disagree.

def consumption_master(item_code):
    """Item name/code header plus every BOM component row (with value) and the total,
    for one item. Returns ``None`` if the item itself doesn't exist."""
    item_code = (item_code or "").strip().upper()
    if not item_code:
        return None
    item = Item.objects.filter(item_code=item_code).values("item_code", "item_name_1").first()
    if not item:
        return None

    rows = list(
        BomComponent.objects.filter(item_code=item_code).values("part_code", "quantity").order_by("part_code")
    )
    part_codes = {r["part_code"] for r in rows}
    parts = {
        p.part_number: p
        for p in Part.objects.filter(part_number__in=part_codes)
    }

    lines = []
    total = Decimal("0")
    for index, r in enumerate(rows, start=1):
        part = parts.get(r["part_code"])
        qty = r["quantity"] or Decimal("0")
        rate = (part.purchase_rate if part else None) or Decimal("0")
        value = (qty * rate).quantize(Decimal("0.01"))
        total += value
        lines.append({
            "sno": index,
            "code": _clean(r["part_code"]),
            "item_description": _clean(part.description_1) if part else "",
            "quantity": f"{qty:.3f}",
            "unit": _clean(part.unit) if part else "",
            "material": _clean(part.material) if part else "",
            "weight_by_100": f"{(part.weight_by_100 or 0):.3f}" if part else "0.000",
            "gauge": _clean(part.gauge) if part else "",
            "drawing_no": _clean(part.drawing_no) if part else "",
            "value": f"{value:.2f}",
        })

    return {
        "item_code": _clean(item["item_code"]),
        "item_name": _clean(item["item_name_1"]),
        "lines": lines,
        "total": f"{total:.2f}",
    }


# --- Bill of Material Master Without Value report -----------------------------------------
#
# Same con-mst data and Part Master reference fields as consumption_master() above, for the
# old VFP screen's "Without Value" Excel button (the commented-out qty*rate/Value(in Rs)/
# Total lines in that macro): no rate lookup, no Value column, no Total row at all.

def bom_without_value(item_code):
    """Item name/code header plus every BOM component row (no value/rate), for one item.
    Returns ``None`` if the item itself doesn't exist."""
    item_code = (item_code or "").strip().upper()
    if not item_code:
        return None
    item = Item.objects.filter(item_code=item_code).values("item_code", "item_name_1").first()
    if not item:
        return None

    rows = list(
        BomComponent.objects.filter(item_code=item_code).values("part_code", "quantity").order_by("part_code")
    )
    part_codes = {r["part_code"] for r in rows}
    parts = {
        p.part_number: p
        for p in Part.objects.filter(part_number__in=part_codes)
    }

    lines = []
    for index, r in enumerate(rows, start=1):
        part = parts.get(r["part_code"])
        qty = r["quantity"] or Decimal("0")
        lines.append({
            "sno": index,
            "code": _clean(r["part_code"]),
            "item_description": _clean(part.description_1) if part else "",
            "quantity": f"{qty:.3f}",
            "unit": _clean(part.unit) if part else "",
            "material": _clean(part.material) if part else "",
            "weight_by_100": f"{(part.weight_by_100 or 0):.3f}" if part else "0.000",
            "gauge": _clean(part.gauge) if part else "",
            "drawing_no": _clean(part.drawing_no) if part else "",
        })

    return {
        "item_code": _clean(item["item_code"]),
        "item_name": _clean(item["item_name_1"]),
        "lines": lines,
    }


# --- Bill of Material Master Value-Wise report (Sub Assembly) -----------------------------
#
# A separate report from consumption_master()/bom_without_value() above: those two read
# con-mst with an Item Master parent (e.g. item 0049). This one reads conms (the SA screen's
# own table, see BomSaComponent) with a PART Master parent (e.g. part ABM01) -- confirmed by
# the old VFP screen's own parent-search code (`sele partmst; do form parthelp2`, not the
# item-master parthelp used by the other two reports) and its Excel macro (`sele conms`).
# Adds HSN Code, P.RATE, S.RATE and Unit; Value = Qty * P.RATE (Part.purchase_rate), never
# S.RATE (Part.sale_rate) -- S.RATE is shown for reference only.

def sa_value_wise(part_code):
    """Parent part name/code plus every SA BOM component row (with HSN, P.RATE, S.RATE
    and Value) and the total, for one part. Returns ``None`` if the part itself doesn't
    exist."""
    part_code = (part_code or "").strip().upper()
    if not part_code:
        return None
    parent = Part.objects.filter(part_number=part_code).values("part_number", "description_1").first()
    if not parent:
        return None

    rows = list(
        BomSaComponent.objects.filter(parent_part_code=part_code)
        .values("component_part_code", "quantity").order_by("component_part_code")
    )
    component_codes = {r["component_part_code"] for r in rows}
    parts = {p.part_number: p for p in Part.objects.filter(part_number__in=component_codes)}

    lines = []
    total = Decimal("0")
    for index, r in enumerate(rows, start=1):
        part = parts.get(r["component_part_code"])
        qty = r["quantity"] or Decimal("0")
        rate = (part.purchase_rate if part else None) or Decimal("0")
        value = (qty * rate).quantize(Decimal("0.01"))
        total += value
        lines.append({
            "sno": index,
            "code": _clean(r["component_part_code"]),
            "item_description": _clean(part.description_1) if part else "",
            "hsn_code": _clean(part.hsn_code) if part else "",
            "quantity": f"{qty:.3f}",
            "unit": _clean(part.unit) if part else "",
            "material": _clean(part.material) if part else "",
            "purchase_rate": f"{(part.purchase_rate or 0):.3f}" if part else "0.000",
            "sale_rate": f"{(part.sale_rate or 0):.2f}" if part else "0.00",
            "drawing_no": _clean(part.drawing_no) if part else "",
            "value": f"{value:.2f}",
        })

    return {
        "item_code": _clean(parent["part_number"]),
        "item_name": _clean(parent["description_1"]),
        "lines": lines,
        "total": f"{total:.2f}",
    }


# --- Bill of Material Master Suppliers report (Sub Assembly, no value) --------------------
#
# A third report over the same SA data as sa_value_wise() above (conms / BomSaComponent,
# Part Master parent like ABM01) -- confirmed by the same "sele conms" Excel macro and
# Part Master parent-search code. No HSN/rates/value here; instead each component's
# Supplier-1..4 (Part.supplier_1..4, party codes) are resolved to party names via the
# existing Party Master (apps.parties.Party) -- no separate supplier master is created.

def sa_without_value_suppliers(part_code):
    """Parent part name/code/unit plus every SA BOM component row (with Supplier-1..4
    names) for one part. Returns ``None`` if the part itself doesn't exist."""
    part_code = (part_code or "").strip().upper()
    if not part_code:
        return None
    parent = Part.objects.filter(part_number=part_code).values("part_number", "description_1", "unit").first()
    if not parent:
        return None

    rows = list(
        BomSaComponent.objects.filter(parent_part_code=part_code)
        .values("component_part_code", "quantity").order_by("component_part_code")
    )
    component_codes = {r["component_part_code"] for r in rows}
    parts = {p.part_number: p for p in Part.objects.filter(part_number__in=component_codes)}

    supplier_codes = set()
    for part in parts.values():
        supplier_codes.update(
            c for c in (part.supplier_1, part.supplier_2, part.supplier_3, part.supplier_4) if c
        )
    party_names = dict(Party.objects.filter(party_code__in=supplier_codes).values_list("party_code", "name"))

    def supplier_name(code):
        return _clean(party_names.get(code, "")) if code else ""

    lines = []
    for index, r in enumerate(rows, start=1):
        part = parts.get(r["component_part_code"])
        qty = r["quantity"] or Decimal("0")
        lines.append({
            "sno": index,
            "code": _clean(r["component_part_code"]),
            "item_description": _clean(part.description_1) if part else "",
            "quantity": f"{qty:.3f}",
            "unit": _clean(part.unit) if part else "",
            "material": _clean(part.material) if part else "",
            "supplier_1": supplier_name(part.supplier_1) if part else "",
            "supplier_2": supplier_name(part.supplier_2) if part else "",
            "supplier_3": supplier_name(part.supplier_3) if part else "",
            "supplier_4": supplier_name(part.supplier_4) if part else "",
        })

    return {
        "item_code": _clean(parent["part_number"]),
        "item_name": _clean(parent["description_1"]),
        "unit": _clean(parent["unit"]),
        "lines": lines,
    }
