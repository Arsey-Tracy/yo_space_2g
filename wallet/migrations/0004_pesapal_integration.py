from django.db import migrations, models
import django.db.models.deletion
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('wallet', '0003_smsbundle_smspurchase'),  # Adjust based on your latest migration
    ]

    operations = [
        # Update SMSPurchase model with PesaPal support
        migrations.AlterField(
            model_name='smspurchase',
            name='amount_paid',
            field=models.DecimalField(decimal_places=2, max_digits=10),
        ),
        # Update payment_method to include choices (previously just a CharField)
        migrations.AlterField(
            model_name='smspurchase',
            name='payment_method',
            field=models.CharField(
                blank=True,
                choices=[
                    ('mobile_money', 'Mobile Money'),
                    ('pesapal', 'PesaPal'),
                    ('iotec', 'ioTec'),
                    ('card', 'Card'),
                ],
                default='pesapal',
                max_length=50,
            ),
        ),
        # Update status to include cancelled choice
        migrations.AlterField(
            model_name='smspurchase',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('completed', 'Completed'),
                    ('failed', 'Failed'),
                    ('cancelled', 'Cancelled'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
        # Add PesaPal-specific tracking fields
        migrations.AddField(
            model_name='smspurchase',
            name='pesapal_order_id',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='smspurchase',
            name='pesapal_tracking_id',
            field=models.CharField(
                blank=True, max_length=100, null=True, unique=True
            ),
        ),
        migrations.AddIndex(
            model_name='smspurchase',
            index=models.Index(
                fields=['organization', '-purchased_at'],
                name='wallet_smspu_organiz_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='smspurchase',
            index=models.Index(
                fields=['payment_reference'],
                name='wallet_smspu_payment_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='smspurchase',
            index=models.Index(
                fields=['pesapal_tracking_id'],
                name='wallet_smspu_pesapal_idx',
            ),
        ),
        migrations.CreateModel(
            name='PesapalPayment',
            fields=[
                (
                    'id',
                    models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID'),
                ),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                (
                    'currency',
                    models.CharField(default='UGX', max_length=3),
                ),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('initiated', 'Initiated'),
                            ('pending', 'Pending'),
                            ('completed', 'Completed'),
                            ('failed', 'Failed'),
                            ('cancelled', 'Cancelled'),
                        ],
                        default='initiated',
                        max_length=20,
                    ),
                ),
                (
                    'order_id',
                    models.CharField(max_length=100, unique=True),
                ),
                (
                    'tracking_id',
                    models.CharField(blank=True, max_length=100, null=True, unique=True),
                ),
                (
                    'merchant_reference',
                    models.CharField(blank=True, max_length=100),
                ),
                (
                    'redirect_url',
                    models.URLField(blank=True),
                ),
                (
                    'customer_email',
                    models.EmailField(blank=True, max_length=254),
                ),
                (
                    'customer_phone',
                    models.CharField(blank=True, max_length=20),
                ),
                (
                    'description',
                    models.TextField(blank=True),
                ),
                (
                    'initiated_at',
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    'verified_at',
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    'completed_at',
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    'last_verified_at',
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    'webhook_data',
                    models.JSONField(blank=True, default=dict),
                ),
                (
                    'organization',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='pesapal_payments',
                        to='account.organization',
                    ),
                ),
                (
                    'sms_purchase',
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='pesapal_payment',
                        to='wallet.smspurchase',
                    ),
                ),
            ],
            options={
                'ordering': ['-initiated_at'],
            },
        ),
        migrations.AddIndex(
            model_name='pesapalpayment',
            index=models.Index(
                fields=['organization', '-initiated_at'],
                name='wallet_pesap_organiz_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='pesapalpayment',
            index=models.Index(
                fields=['order_id'],
                name='wallet_pesap_order_id_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='pesapalpayment',
            index=models.Index(
                fields=['tracking_id'],
                name='wallet_pesap_tracking_idx',
            ),
        ),
    ]
