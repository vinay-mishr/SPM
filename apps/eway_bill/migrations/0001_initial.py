# Generated for apps.eway_bill

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='EwayBill',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('bill_no', models.CharField(max_length=10, unique=True, verbose_name='GST bill no')),
                ('status', models.CharField(choices=[('NOT_GENERATED', 'Not Generated'), ('PENDING', 'Pending'), ('GENERATED', 'Generated'), ('FAILED', 'Failed'), ('CANCELLED', 'Cancelled')], default='NOT_GENERATED', max_length=20)),
                ('irn', models.CharField(blank=True, max_length=64, verbose_name='IRN')),
                ('ack_no', models.CharField(blank=True, max_length=20, verbose_name='acknowledgement no')),
                ('ack_date', models.DateTimeField(blank=True, null=True)),
                ('signed_qr_code', models.TextField(blank=True)),
                ('eway_bill_no', models.CharField(blank=True, max_length=20, verbose_name='e-way bill no')),
                ('eway_bill_date', models.DateTimeField(blank=True, null=True)),
                ('valid_upto', models.DateTimeField(blank=True, null=True)),
                ('provider', models.CharField(default='charteredinfo', max_length=30)),
                ('environment', models.CharField(default='sandbox', max_length=10)),
                ('transporter_gstin', models.CharField(blank=True, max_length=15)),
                ('transporter_name', models.CharField(blank=True, max_length=100)),
                ('transport_mode', models.CharField(blank=True, choices=[('1', 'Road'), ('2', 'Rail'), ('3', 'Air'), ('4', 'Ship')], max_length=1)),
                ('transport_doc_no', models.CharField(blank=True, max_length=20)),
                ('transport_doc_date', models.DateField(blank=True, null=True)),
                ('vehicle_no', models.CharField(blank=True, max_length=20)),
                ('distance_km', models.PositiveIntegerField(blank=True, null=True)),
                ('recipient_pincode', models.CharField(blank=True, max_length=6)),
                ('last_error', models.TextField(blank=True)),
                ('last_request', models.TextField(blank=True)),
                ('last_response', models.TextField(blank=True)),
                ('generated_by', models.CharField(blank=True, max_length=60)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'E-Way Bill',
            },
        ),
        migrations.CreateModel(
            name='EwayAuthToken',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('provider', models.CharField(max_length=30, unique=True)),
                ('token', models.TextField()),
                ('sek', models.TextField(blank=True)),
                ('expires_at', models.DateTimeField()),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'E-Way Bill provider token',
            },
        ),
        migrations.CreateModel(
            name='EwayBillLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(max_length=20)),
                ('request_payload', models.TextField(blank=True)),
                ('response_payload', models.TextField(blank=True)),
                ('success', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('eway_bill', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='logs', to='eway_bill.ewaybill')),
            ],
            options={
                'verbose_name': 'E-Way Bill API log',
                'ordering': ['-created_at'],
            },
        ),
    ]
