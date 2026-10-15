"""
Party Master now maps the old software's cust_mst table (SP_MACHINE, unmanaged).

- Drops the empty local table ``parties_party`` (approved 25 Sep 2026; it never held data).
- Registers ``Party`` as an unmanaged model on ``cust_mst``: Django never creates,
  alters or drops that table. Migrations never run on the SP_MACHINE database at all
  (config.db_routers.LegacyRouter.allow_migrate returns False for it).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("parties", "0001_initial"),
    ]

    operations = [
        migrations.DeleteModel(name="Party"),
        migrations.CreateModel(
            name="Party",
            fields=[
                ("party_code", models.CharField(db_column="ccode", max_length=4, primary_key=True, serialize=False, verbose_name="party code")),
            ],
            options={
                "verbose_name": "party",
                "verbose_name_plural": "parties",
                "db_table": "cust_mst",
                "ordering": ["name"],
                "managed": False,
            },
        ),
    ]
