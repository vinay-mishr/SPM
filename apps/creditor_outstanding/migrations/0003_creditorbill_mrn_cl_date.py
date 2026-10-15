from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('creditor_outstanding', '0002_advancefile'),
    ]

    operations = [
        migrations.AddField(
            model_name='creditorbill',
            name='mrn_no',
            field=models.CharField(blank=True, db_column='mrn_no', max_length=10, null=True),
        ),
        migrations.AddField(
            model_name='creditorbill',
            name='cl_date',
            field=models.DateField(blank=True, db_column='cl_date', null=True),
        ),
    ]
