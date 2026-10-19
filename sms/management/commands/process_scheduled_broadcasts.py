from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from wallet.models import Wallet
from wallet.services import InsufficientCreditsError

from sms.models import Broadcast
from sms.providers import send_bulk_sms
from sms.services import SmsDeliveryError, deliver_scheduled_broadcast


class Command(BaseCommand):
    help = "Send due SMS broadcasts scheduled by organization owners."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Maximum number of due broadcasts to process in one run.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit < 1:
            raise CommandError("--limit must be a positive integer.")

        sent_count = 0
        failed_count = 0

        for _ in range(limit):
            with transaction.atomic():
                broadcast = (
                    Broadcast.objects.select_for_update(
                        skip_locked=True,
                        of=("self",),
                    )
                    .select_related("space", "space__organization", "created_by")
                    .filter(status="scheduled", scheduled_at__lte=timezone.now())
                    .order_by("scheduled_at", "pk")
                    .first()
                )
                if broadcast is None:
                    break

                # Claim the row before contacting the provider so overlapping cron runs cannot send it twice.
                broadcast.status = "sending"
                broadcast.save(update_fields=["status"])

            try:
                deliver_scheduled_broadcast(
                    broadcast=broadcast,
                    sms_sender=send_bulk_sms,
                )
            except (
                InsufficientCreditsError,
                SmsDeliveryError,
                ValueError,
                Wallet.DoesNotExist,
            ) as exc:
                Broadcast.objects.filter(
                    pk=broadcast.pk, status="sending"
                ).update(status="failed", failure_reason=str(exc))
                failed_count += 1
                self.stderr.write(
                    f"Broadcast {broadcast.pk} failed: {exc}"
                )
            else:
                sent_count += 1

        processed_count = sent_count + failed_count
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {processed_count} scheduled broadcast(s): "
                f"{sent_count} sent, {failed_count} failed."
            )
        )
