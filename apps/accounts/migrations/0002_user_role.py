from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[('ADMIN', 'Admin'), ('SALES', 'Sales')],
                default='SALES',
                max_length=10,
            ),
        ),
    ]
