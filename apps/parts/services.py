"""Part Master logic (old software's part-mst). Views stay thin and call these."""
from django.conf import settings
from django.db import transaction

from apps.materials.models import Material
from apps.parties.models import Party
from config.legacy import fill_blank_columns, tables_using

from .models import Part

DECIMAL_FIELDS = [
    "quantity_in_order", "gross_weight", "purchase_rate", "sale_rate", "opening_stock", "reorder_qty",
    "weight_by_100", "current_stock", "gst_percent", "rate_1", "rate_2", "rate_3", "rate_4",
]
TEXT_FIELDS = [
    "description_1", "description_2", "drawing_no", "gauge", "grade", "material", "location", "unit",
    "hsn_code", "supplier_1", "supplier_2", "supplier_3", "supplier_4",
]

# Tables that hold BOM / production / history rows against a part number (icod).
USAGE_TABLES = [
    ("apc", "icod"), ("bhu", "icod"), ("bhui", "icod"), ("bhupi", "icod"), ("conms", "icod"),
    ("con-mst", "icod"), ("parthis", "icod"), ("se", "icod"), ("sec", "icod"), ("sep", "icod"),
    ("ser", "icod"), ("vs", "icod"), ("vsc", "icod"), ("vsp", "icod"), ("vsr", "icod"),
]


class PartError(Exception):
    """A save / delete that must be refused, with a message for the user."""


def writes_enabled():
    return "legacy" not in settings.DATABASES or settings.LEGACY_WRITES_ENABLED


def _db():
    return Part.objects.db


def _clean(value):
    return (value or "").strip()


def duplicate_part_numbers():
    """Part numbers shared by more than one old row (protected from MODIFY/DELETE)."""
    from django.db.models import Count

    return set(
        Part.objects.values_list("part_number", flat=True)
        .annotate(n=Count("part_number"))
        .filter(n__gt=1)
    )


def _decimal(value):
    return str(value) if value is not None else "0.00"


def serialize(part):
    data = {"id": part.part_number, "part_number": _clean(part.part_number), "sub_assembly": _clean(part.sub_assembly) == "Y",
            "part_type": _clean(part.part_type)}
    for field in TEXT_FIELDS:
        data[field] = _clean(getattr(part, field))
    for field in DECIMAL_FIELDS:
        data[field] = _decimal(getattr(part, field))
    data["packing"] = int(part.packing) if part.packing is not None else 0
    return data


def list_parts():
    return [serialize(p) for p in Part.objects.order_by("part_number")]


def material_names():
    """Material Master names, for the MATERIAL field's suggestions/Help lookup."""
    return sorted({n.strip() for n in Material.objects.values_list("name", flat=True) if n and n.strip()})


def party_names(codes):
    codes = [c for c in codes if c]
    return dict(Party.objects.filter(party_code__in=codes).values_list("party_code", "name"))


def search_parties(term, limit=15):
    """Party Master lookup by code or name (for the SUPPLIER fields)."""
    term = (term or "").strip()
    if term:
        qs = Party.objects.filter(party_code__istartswith=term) | Party.objects.filter(name__icontains=term)
    else:
        qs = Party.objects.all()
    return [
        {"code": c, "name": (n or "").strip(), "city": (city or "").strip()}
        for c, n, city in qs.order_by("name").values_list("party_code", "name", "city")[:limit]
    ]


def create(data, username=""):
    if Part.objects.filter(part_number=data["part_number"]).exists():
        raise PartError(f"Part No. {data['part_number']} already exists.")
    with transaction.atomic(using=_db()):
        part = Part(part_number=data["part_number"], sub_assembly="Y" if data["sub_assembly"] else "", part_type=data["part_type"])
        for field in TEXT_FIELDS + DECIMAL_FIELDS:
            setattr(part, field, data[field])
        part.packing = data["packing"]
        part.save(force_insert=True)
        fill_blank_columns(_db(), "part-mst", "icod", part.part_number, username)
    return part


def update(part, data):
    # Part No. is the master identifier: protected from change once created (like Item Master's code).
    part.sub_assembly = "Y" if data["sub_assembly"] else ""
    part.part_type = data["part_type"]
    for field in TEXT_FIELDS + DECIMAL_FIELDS:
        setattr(part, field, data[field])
    part.packing = data["packing"]
    part.save(force_update=True)
    return part


def delete(part):
    used_in = tables_using(_db(), USAGE_TABLES, part.part_number)
    if used_in:
        raise PartError(
            f"Part {part.part_number} cannot be deleted because it is used in: {', '.join(used_in)}."
        )
    part.delete()
