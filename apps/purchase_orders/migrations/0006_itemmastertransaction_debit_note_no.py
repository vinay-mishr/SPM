from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('purchase_orders', '0005_pendinglettersharelink'),
    ]

    operations = [
        migrations.AddField(
            model_name='itemmastertransaction',
            name='debit_note_no',
            field=models.CharField(blank=True, db_column='gdb_no', max_length=10, null=True, verbose_name='debit note no'),
        ),
        migrations.AddField(
            model_name='itemmastertransaction',
            name='debit_note_date',
            field=models.DateField(blank=True, db_column='gdb_dt', null=True, verbose_name='debit note date'),
        ),
    ]
