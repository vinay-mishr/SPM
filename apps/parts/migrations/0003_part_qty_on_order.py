from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("parts", "0002_alter_part_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="part",
            name="qty_on_order",
            field=models.DecimalField(
                blank=True, decimal_places=3, db_column="p_order1", max_digits=11, null=True,
                verbose_name="qty on order",
            ),
        ),
    ]
