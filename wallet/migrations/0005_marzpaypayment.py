from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('wallet', '0004_pesapal_integration'),
    ]

    operations = [
        migrations.CreateModel(
            name='MarzpayPayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('currency', models.CharField(default='UGX', max_length=3)),
                ('status', models.CharField(choices=[('initiated', 'Initiated'), ('processing', 'Processing'), ('completed', 'Completed'), ('failed', 'Failed'), ('cancelled', 'Cancelled')], default='initiated', max_length=20)),
                ('reference', models.CharField(max_length=100, unique=True)),
                ('transaction_uuid', models.CharField(blank=True, max_length=100, null=True, unique=True)),
                ('provider_transaction_id', models.CharField(blank=True, max_length=100, null=True)),
                ('customer_phone', models.CharField(max_length=20)),
                ('description', models.TextField(blank=True)),
                ('initiated_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('last_updated_at', models.DateTimeField(auto_now=True)),
                ('webhook_data', models.JSONField(blank=True, default=dict)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='marzpay_payments', to='account.organization')),
                ('sms_purchase', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='marzpay_payment', to='wallet.smspurchase')),
            ],
            options={
                'ordering': ['-initiated_at'],
            },
        ),
        migrations.AddIndex(
            model_name='marzpaypayment',
            index=models.Index(fields=['organization', '-initiated_at'], name='wallet_marzp_organiz_idx'),
        ),
        migrations.AddIndex(
            model_name='marzpaypayment',
            index=models.Index(fields=['reference'], name='wallet_marzp_reference_idx'),
        ),
        migrations.AddIndex(
            model_name='marzpaypayment',
            index=models.Index(fields=['transaction_uuid'], name='wallet_marzp_transac_idx'),
        ),
    ]
