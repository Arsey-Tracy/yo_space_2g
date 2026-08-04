from django.core.management.base import BaseCommand
from wallet.models import TelecomNetwork

class Command(BaseCommand):
    help = 'Seeds Pay-As-You-Go telecom networks with provider costs, markups, and selling prices.'

    def handle(self, *args, **options):
        networks = [
            {
                'name': 'MTN Uganda',
                'code': 'MTN',
                'provider_cost_ugx': 27,
                'markup_ugx': 13,
                'selling_price_ugx': 40,
                'is_active': True
            },
            {
                'name': 'Airtel Uganda',
                'code': 'AIRTEL',
                'provider_cost_ugx': 25,
                'markup_ugx': 15,
                'selling_price_ugx': 40,
                'is_active': True
            },
            {
                'name': 'Other Telcos (Lyca / Others)',
                'code': 'OTHER',
                'provider_cost_ugx': 35,
                'markup_ugx': 15,
                'selling_price_ugx': 50,
                'is_active': True
            },
        ]

        for net in networks:
            obj, created = TelecomNetwork.objects.update_or_create(
                code=net['code'],
                defaults=net
            )
            action = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{action} {obj.name}: Base {obj.provider_cost_ugx} UGX + Markup {obj.markup_ugx} UGX = {obj.selling_price_ugx} UGX"))
