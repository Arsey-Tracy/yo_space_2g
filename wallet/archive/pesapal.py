class InitiatePesapalPaymentView(APIView):
    """Initiate a PesaPal payment for SMS credits."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
            if not data.get("email"):
                data["email"] = getattr(request.user, "email", "") or ""
            serializer = InitiatePesapalPaymentSerializer(data=data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            org = get_organization_for_user(request.user)
            if not org:
                return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)

            try:
                pesapal_payment, _purchase, payment_result = start_pesapal_wallet_topup(
                    user=request.user,
                    org=org,
                    amount=serializer.validated_data.get("amount"),
                    phone_number=serializer.validated_data["phone_number"],
                    email=serializer.validated_data.get("email") or request.user.email,
                    bundle_id=serializer.validated_data.get("bundle_id"),
                    description=serializer.validated_data.get("description", "SMS Credits Purchase"),
                )
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
            except PesapalError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

            return Response({
                "message": "Payment initiated successfully",
                "payment": PesapalPaymentSerializer(pesapal_payment).data,
                "redirect_url": payment_result.get("redirect_url"),
                "tracking_id": payment_result.get("order_tracking_id"),
            }, status=status.HTTP_201_CREATED)

        except Exception as exc:
            logger.exception("Failed to initiate PesaPal payment: %s", exc)
            return Response(
                {"detail": f"Error: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class VerifyPesapalPaymentView(APIView):
    """Verify PesaPal payment status and credit wallet."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return self._verify(
            request,
            request.query_params.get("tracking_id") or request.query_params.get("OrderTrackingId"),
        )

    def post(self, request):
        serializer = VerifyPesapalPaymentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return self._verify(request, serializer.validated_data["tracking_id"])

    def _verify(self, request, tracking_id):
        try:
            if not tracking_id:
                return Response({"detail": "tracking_id is required."}, status=status.HTTP_400_BAD_REQUEST)

            org = get_organization_for_user(request.user)
            if not org:
                return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)

            pesapal_payment = PesapalPayment.objects.filter(
                tracking_id=tracking_id, organization=org
            ).first()
            if not pesapal_payment:
                pesapal_payment = PesapalPayment.objects.filter(
                    order_id=tracking_id, organization=org
                ).first()
            if not pesapal_payment:
                return Response({"detail": "Payment not found."}, status=status.HTTP_404_NOT_FOUND)

            pesapal_payment = verify_and_apply_pesapal_payment(pesapal_payment)
            payment_status = pesapal_payment.status
            wallet_balance = (
                get_or_create_wallet(org).balance_credits if payment_status == "completed" else None
            )
            return Response({
                "message": "Payment verified",
                "payment": PesapalPaymentSerializer(pesapal_payment).data,
                "wallet_balance": wallet_balance,
            }, status=status.HTTP_200_OK)
        except PesapalError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception("Failed to verify PesaPal payment: %s", exc)
            return Response(
                {"detail": f"Error: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PesapalCallbackView(APIView):
    """IPN webhook and browser return URL for PesaPal."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return self._handle(request, request.query_params)

    def post(self, request):
        payload = request.data if hasattr(request.data, "get") else {}
        merged = {**request.query_params.dict(), **(payload if isinstance(payload, dict) else {})}
        return self._handle(request, merged)

    def _handle(self, request, payload):
        try:
            tracking_id = (
                payload.get("OrderTrackingId")
                or payload.get("orderTrackingId")
                or payload.get("tracking_id")
            )
            order_id = (
                payload.get("OrderMerchantReference")
                or payload.get("orderMerchantReference")
                or payload.get("order_id")
            )
            if not tracking_id and not order_id:
                return Response(
                    {"detail": "Missing tracking_id or order_id"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            pesapal_payment = None
            if tracking_id:
                pesapal_payment = PesapalPayment.objects.filter(tracking_id=tracking_id).first()
            if not pesapal_payment and order_id:
                pesapal_payment = PesapalPayment.objects.filter(order_id=order_id).first()

            if not pesapal_payment:
                logger.warning("Received PesaPal callback for unknown order: %s / %s", order_id, tracking_id)
            else:
                pesapal_payment.webhook_data = payload.dict() if hasattr(payload, "dict") else dict(payload)
                update_fields = ["webhook_data", "last_verified_at"]
                pesapal_payment.last_verified_at = timezone.now()
                if tracking_id and not pesapal_payment.tracking_id:
                    pesapal_payment.tracking_id = tracking_id
                    update_fields.append("tracking_id")
                pesapal_payment.save(update_fields=update_fields)
                if pesapal_payment.tracking_id:
                    verify_and_apply_pesapal_payment(pesapal_payment)

            accept = request.META.get("HTTP_ACCEPT", "")
            if "text/html" in accept:
                from django.shortcuts import redirect
                return redirect(
                    frontend_billing_callback_url(tracking_id=tracking_id or "", order_id=order_id or "")
                )
            return Response({"received": True}, status=status.HTTP_200_OK)
        except Exception as exc:
            logger.exception("PesaPal callback error: %s", exc)
            return Response({"received": True}, status=status.HTTP_200_OK)
