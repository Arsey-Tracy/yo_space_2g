def send_payment_confirmation_sms(payment_id: int):
    try:
        payment = PesapalPayment.objects.select_related("organization", "sms_purchase").get(pk=payment_id)
        phone = payment.customer_phone
        if not phone:
            return
        wallet = get_or_create_wallet(payment.organization)
        credits = payment.sms_purchase.sms_count if payment.sms_purchase else 0
        message = (
            f"YoSpaces confirmed your payment of UGX {int(payment.amount):,}. "
            f"{credits} SMS credits added. New balance: {wallet.balance_credits}."
        )
        from sms.views import send_bulk_sms
        send_bulk_sms([phone], message, org_name=payment.organization.name)
    except Exception:
        logger.exception("Failed to send YoSpaces payment confirmation SMS for payment %s", payment_id)


def apply_completed_pesapal_payment(pesapal_payment: PesapalPayment) -> PesapalPayment:
    """Idempotently credit the wallet after PesaPal reports a completed payment."""
    payment_id = pesapal_payment.pk
    with db_transaction.atomic():
        payment = (
            PesapalPayment.objects.select_for_update()
            .select_related("sms_purchase", "organization")
            .filter(pk=payment_id)
            .first()
        )
        if not payment:
            return pesapal_payment

        purchase = payment.sms_purchase
        if purchase:
            purchase = SMSPurchase.objects.select_for_update().filter(pk=purchase.pk).first()

        if purchase and purchase.status == "completed":
            payment.status = "completed"
            payment.last_verified_at = timezone.now()
            update_fields = ["status", "last_verified_at"]
            if not payment.completed_at:
                payment.completed_at = timezone.now()
                update_fields.append("completed_at")
            payment.save(update_fields=update_fields)
            return payment

        credits = purchase.sms_count if purchase else compute_purchase_credits(int(payment.amount or 0))
        wallet = get_or_create_wallet(payment.organization)
        wallet.balance_credits += credits
        wallet.save(update_fields=["balance_credits"])

        if purchase:
            purchase.status = "completed"
            purchase.pesapal_tracking_id = payment.tracking_id
            purchase.save(update_fields=["status", "pesapal_tracking_id"])

        org = payment.organization
        if hasattr(org, "sms_balance"):
            org.sms_balance = wallet.balance_credits
            org.save(update_fields=["sms_balance"])

        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="topup",
            amount_paid_ugx=int(payment.amount or 0),
            credits_added=credits,
            payment_method="pesapal",
            payment_reference=payment.tracking_id or payment.order_id,
            notes=f"PesaPal payment {payment.order_id}",
        )

        payment.status = "completed"
        payment.completed_at = timezone.now()
        payment.last_verified_at = timezone.now()
        payment.save(update_fields=["status", "completed_at", "last_verified_at"])
        db_transaction.on_commit(lambda: send_payment_confirmation_sms(payment_id))
    return PesapalPayment.objects.get(pk=payment_id)


def verify_and_apply_pesapal_payment(pesapal_payment: PesapalPayment) -> PesapalPayment:
    service = PesapalPaymentService()
    result = service.verify_payment(pesapal_payment.tracking_id)
    if not result.get("success"):
        raise PesapalError(result.get("error") or "Failed to verify PesaPal payment")

    payment_status = result.get("status") or "pending"
    pesapal_payment.last_verified_at = timezone.now()
    pesapal_payment.status = payment_status
    pesapal_payment.save(update_fields=["status", "last_verified_at"])

    if payment_status == "completed":
        return apply_completed_pesapal_payment(pesapal_payment)
    if payment_status in {"failed", "cancelled"} and pesapal_payment.sms_purchase:
        purchase = pesapal_payment.sms_purchase
        if purchase.status == "pending":
            purchase.status = payment_status if payment_status in {"failed", "cancelled"} else "failed"
            purchase.save(update_fields=["status"])
    return pesapal_payment


def start_pesapal_wallet_topup(*, user, org, amount, phone_number, email, bundle_id=None, description="SMS Credits Purchase"):
    bundle = None
    if bundle_id:
        bundle = SMSBundle.objects.filter(id=bundle_id, is_active=True).first()
        if not bundle:
            raise ValueError("Bundle not found.")
        amount_ugx = int(bundle.price)
        sms_count = bundle.sms_count
        description = description or f"SMS Credits - {bundle.name}"
    else:
        amount_ugx = int(amount)
        sms_price = getattr(settings, "SMS_PRICE_OTHER_UGX", 50)
        sms_count = max(1, int(amount_ugx / sms_price))
        description = description or f"SMS Credits - {sms_count} SMS"

    phone = normalize_phone_number(phone_number)
    order_id = f"yospace-{org.id}-{uuid4().hex[:8]}"
    user_callback = frontend_billing_callback_url()

    with db_transaction.atomic():
        pesapal_payment = PesapalPayment.objects.create(
            organization=org,
            amount=amount_ugx,
            currency="UGX",
            order_id=order_id,
            customer_email=email or "",
            customer_phone=phone,
            description=description,
        )
        sms_purchase = SMSPurchase.objects.create(
            organization=org,
            bundle=bundle,
            sms_count=sms_count,
            amount_paid=amount_ugx,
            status="pending",
            payment_method="pesapal",
            payment_reference=order_id,
            pesapal_order_id=order_id,
            purchased_by=user,
        )
        pesapal_payment.sms_purchase = sms_purchase
        pesapal_payment.save(update_fields=["sms_purchase"])

    service = PesapalPaymentService()
    billing_address = {
        "email_address": email or getattr(user, "email", "") or "billing@yospacesug.com",
        "phone_number": phone,
        "country_code": "UG",
        "first_name": getattr(user, "first_name", "") or getattr(user, "username", "YoSpaces"),
        "last_name": getattr(user, "last_name", "") or "Customer",
    }
    payment_result = service.initiate_payment(
        order_id=order_id,
        amount=float(amount_ugx),
        description=description,
        callback_url=user_callback,
        notification_id=settings.PESAPAL_NOTIFICATION_ID,
        billing_address=billing_address,
        customer_email=email,
        customer_phone=phone,
    )
    if not payment_result.get("success"):
        pesapal_payment.status = "failed"
        pesapal_payment.save(update_fields=["status"])
        sms_purchase.status = "failed"
        sms_purchase.save(update_fields=["status"])
        raise PesapalError(payment_result.get("error") or "Failed to initiate PesaPal payment")

    pesapal_payment.tracking_id = payment_result.get("order_tracking_id")
    pesapal_payment.merchant_reference = payment_result.get("merchant_reference") or order_id
    pesapal_payment.redirect_url = payment_result.get("redirect_url") or ""
    pesapal_payment.status = "initiated"
    pesapal_payment.save(update_fields=["tracking_id", "merchant_reference", "redirect_url", "status"])

    if pesapal_payment.tracking_id:
        sms_purchase.pesapal_tracking_id = pesapal_payment.tracking_id
        sms_purchase.save(update_fields=["pesapal_tracking_id"])

    return pesapal_payment, sms_purchase, payment_result


def confirm_purchase_from_provider(external_id):
    """Confirm a pending top-up by merchant reference or PesaPal tracking id."""
    payment = (
        PesapalPayment.objects.filter(order_id=external_id).first()
        or PesapalPayment.objects.filter(tracking_id=external_id).first()
        or PesapalPayment.objects.filter(merchant_reference=external_id).first()
    )
    if not payment:
        purchase = SMSPurchase.objects.filter(payment_reference=external_id).select_related("organization").first()
        return purchase
    if not payment.tracking_id:
        return payment.sms_purchase
    updated = verify_and_apply_pesapal_payment(payment)
    return updated.sms_purchase


class PaymentCallbackView(APIView):
    """Public webhook target for ioTec. CRITICAL: the request body's
    claimed status is NEVER trusted directly -- it only tells us which
    external_id to go re-verify. confirm_purchase_from_provider makes its
    own authenticated call back to ioTec before crediting anything, so a
    forged POST to this endpoint cannot manufacture free credits."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        external_id = request.data.get("externalId") or request.data.get("external_id")
        if not external_id:
            return Response({"detail": "Missing external id."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            confirm_purchase_from_provider(external_id)
        except requests.RequestException as exc:
            # Still 200 -- ioTec may retry on non-2xx, and retrying won't
            # fix a network error on our side. Log it, respond OK, let the
            # next poll or retry pick it up.
            import logging
            logging.getLogger(__name__).error("Callback verification failed for %s: %s", external_id, exc)

        return Response({"received": True, "external_id": external_id})


class PaymentCollectionStatusView(APIView):
    """Frontend polls this after PurchaseSMSView. Safe to call repeatedly
    -- confirm_purchase_from_provider is idempotent."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, external_id):
        org = get_organization_for_user(request.user)
        if not org:
            return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            purchase = confirm_purchase_from_provider(external_id)
        except PesapalError as exc:
            return Response({"detail": f"Payment provider request failed: {exc}"}, status=status.HTTP_502_BAD_GATEWAY)

        if not purchase or purchase.organization_id != org.id:
            return Response({"detail": "Purchase not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "organization": org.name,
            "external_id": external_id,
            "status": purchase.status,
            "wallet_balance": get_or_create_wallet(org).balance_credits,
       })



class PesapalPayment(models.Model):
    """Track PesaPal payment transactions."""
    STATUS_CHOICES = [
        ('initiated', 'Initiated'),
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    organization = models.ForeignKey('account.Organization', on_delete=models.CASCADE, related_name='pesapal_payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='UGX')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='initiated')
    
    # PesaPal references
    order_id = models.CharField(max_length=100, unique=True)
    tracking_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    merchant_reference = models.CharField(max_length=100, blank=True)
    redirect_url = models.URLField(blank=True)
    
    # Associated SMS purchase
    sms_purchase = models.OneToOneField(SMSPurchase, on_delete=models.SET_NULL, null=True, blank=True, related_name='pesapal_payment')
    
    # Payment details
    customer_email = models.EmailField(blank=True)
    customer_phone = models.CharField(max_length=20, blank=True)
    description = models.TextField(blank=True)
    
    # Tracking
    initiated_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    
    # Webhook data
    webhook_data = models.JSONField(default=dict, blank=True)
    
    class Meta:
        ordering = ['-initiated_at']
        indexes = [
            models.Index(fields=['organization', '-initiated_at']),
            models.Index(fields=['order_id']),
            models.Index(fields=['tracking_id']),
        ]

    def __str__(self):
        return f"PesaPal Payment - {self.amount} {self.currency} ({self.status})"


# serialozers

class PesapalPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PesapalPayment
        fields = [
            'id', 'organization', 'amount', 'currency', 'status', 'order_id',
            'tracking_id', 'merchant_reference', 'redirect_url', 'customer_email',
            'customer_phone', 'description', 'initiated_at', 'verified_at',
            'completed_at', 'last_verified_at'
        ]
        read_only_fields = [
            'id', 'tracking_id', 'redirect_url', 'initiated_at', 'verified_at',
            'completed_at', 'last_verified_at'
        ]


class InitiatePesapalPaymentSerializer(serializers.Serializer):
    """Serializer for initiating a PesaPal payment."""
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0.01, required=False)
    description = serializers.CharField(max_length=500, required=False, default='SMS Credits Purchase')
    phone_number = serializers.CharField(max_length=20)
    email = serializers.EmailField(required=False, allow_blank=True)
    bundle_id = serializers.IntegerField(required=False)

    def validate(self, attrs):
        if not attrs.get("bundle_id") and attrs.get("amount") is None:
            raise serializers.ValidationError("Provide a bundle_id or a custom amount.")
        return attrs


class VerifyPesapalPaymentSerializer(serializers.Serializer):
    """Serializer for verifying a PesaPal payment."""
    tracking_id = serializers.CharField(max_length=100)
