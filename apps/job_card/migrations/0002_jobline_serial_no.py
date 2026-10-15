from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("job_card", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobline",
            name="serial_no",
            field=models.CharField(blank=True, db_column="jo_no", max_length=9, null=True, verbose_name="serial no"),
        ),
    ]
