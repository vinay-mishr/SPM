from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gl', '0002_alter_ledger_options'),
    ]

    operations = [
        migrations.AddField(
            model_name='ledger',
            name='gl_type',
            field=models.CharField(blank=True, db_column='gl_type', max_length=10, null=True, verbose_name='group (tree)'),
        ),
    ]
