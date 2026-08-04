from django.core.management.base import BaseCommand
from subscriptions.models import Subscription, SMSBundle


class Command(BaseCommand):
    help = 'Seeds subscription tiers and SMS top-up bundles into database'

    def handle(self, *args, **options):
        plans = [
            {
                'name': 'Standard',
                'price': 200000.00,
                'duration_in_days': 30,
                'max_spaces': 1,
                'max_members_per_space': 100,
                'monthly_sms_quota': 1000,
                'allow_merge_spaces': False,
                'allow_public_private': False,
                'allow_analytics': False,
                'allow_reports': False,
                'allow_surveys': False,
                'features': '1 Space, Up to 100 members, 1,000 Bulk SMS/mo, Dashboard access',
            },
            {
                'name': 'Pro',
                'price': 350000.00,
                'duration_in_days': 30,
                'max_spaces': 3,
                'max_members_per_space': 300,
                'monthly_sms_quota': 3000,
                'allow_merge_spaces': True,
                'allow_public_private': True,
                'allow_analytics': True,
                'allow_reports': False,
                'allow_surveys': False,
                'features': '3 Spaces, Up to 300 members/space, 3,000 Bulk SMS/mo, Merge Spaces, Public & Private Spaces, Analytics',
            },
            {
                'name': 'Premium',
                'price': 500000.00,
                'duration_in_days': 30,
                'max_spaces': 10,
                'max_members_per_space': 1000,
                'monthly_sms_quota': 10000,
                'allow_merge_spaces': True,
                'allow_public_private': True,
                'allow_analytics': True,
                'allow_reports': True,
                'allow_surveys': True,
                'features': '10 Spaces, Up to 1,000 members/space, 10,000 Bulk SMS/mo, Merge Spaces, Analytics, Report Generation, Survey & Poll Management',
            },
            {
                'name': 'Enterprise',
                'price': 1000000.00,
                'duration_in_days': 30,
                'max_spaces': 999,
                'max_members_per_space': 100000,
                'monthly_sms_quota': 50000,
                'allow_merge_spaces': True,
                'allow_public_private': True,
                'allow_analytics': True,
                'allow_reports': True,
                'allow_surveys': True,
                'features': 'Unlimited Spaces, Unlimited Members, Custom SMS bundles, Voice conferencing, White-label branding, Dedicated Account Manager',
            },
        ]

        for p in plans:
            sub, created = Subscription.objects.update_or_create(
                name=p['name'],
                defaults=p
            )
            action = 'Created' if created else 'Updated'
            self.stdout.write(self.style.SUCCESS(f"{action} plan '{sub.name}'"))

        # Seed SMS Top-Up Bundles (Pay-As-You-Go)
        bundles = [
            {'name': 'Starter Pack',     'sms_count': 500,   'price': 25000.00},
            {'name': 'Basic Bundle',     'sms_count': 1000,  'price': 45000.00},
            {'name': 'Growth Bundle',    'sms_count': 3000,  'price': 120000.00},
            {'name': 'Pro Bundle',       'sms_count': 5000,  'price': 180000.00},
            {'name': 'Mega Bundle',      'sms_count': 10000, 'price': 320000.00},
            {'name': 'Enterprise Pack',  'sms_count': 50000, 'price': 1400000.00},
        ]

        for b in bundles:
            bundle, created = SMSBundle.objects.update_or_create(
                name=b['name'],
                defaults=b
            )
            action = 'Created' if created else 'Updated'
            self.stdout.write(self.style.SUCCESS(
                f"{action} SMS bundle '{bundle.name}' ({bundle.sms_count} SMS @ UGX {bundle.price:,.0f}, UGX {bundle.price_per_sms:.0f}/sms)"
            ))

