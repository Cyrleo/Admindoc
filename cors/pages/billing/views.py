from datetime import datetime, timezone
import os

import stripe
from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from stripe import SignatureVerificationError

from cors.models import Subscription
from .serializers import CheckoutSessionSerializer


class CreateCheckoutSessionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=CheckoutSessionSerializer)
    def post(self, request):
        serializer = CheckoutSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        secret_key = os.getenv("STRIPE_SECRET_KEY", "")
        if not secret_key:
            return Response(
                {"detail": "Stripe is not configured. Missing STRIPE_SECRET_KEY."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        stripe.api_key = secret_key
        payload = dict(serializer.validated_data)
        subscription, _ = Subscription.objects.get_or_create(user=request.user)

        customer_id = subscription.stripe_customer_id
        if not customer_id:
            customer = stripe.Customer.create(email=request.user.email)
            customer_id = customer.id
            subscription.stripe_customer_id = customer_id
            subscription.save(update_fields=["stripe_customer_id", "updated_at"])

        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": payload["price_id"], "quantity": 1}],
            success_url=payload["success_url"],
            cancel_url=payload["cancel_url"],
            metadata={
                "user_id": str(request.user.pk),
                "plan": payload.get("plan", ""),
            },
        )

        return Response({"checkout_url": session.url, "session_id": session.id}, status=status.HTTP_201_CREATED)


class StripeWebhookView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        secret_key = os.getenv("STRIPE_SECRET_KEY", "")
        webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
        if not secret_key or not webhook_secret:
            return Response(
                {"detail": "Stripe webhook is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        stripe.api_key = secret_key
        payload = request.body
        signature = request.headers.get("Stripe-Signature", "")

        try:
            event = stripe.Webhook.construct_event(payload, signature, webhook_secret)
        except ValueError:
            return Response({"detail": "Invalid payload."}, status=status.HTTP_400_BAD_REQUEST)
        except SignatureVerificationError:
            return Response({"detail": "Invalid signature."}, status=status.HTTP_400_BAD_REQUEST)

        event_type = event.get("type")
        data = event.get("data", {}).get("object", {})

        if event_type in {"checkout.session.completed", "customer.subscription.created", "customer.subscription.updated"}:
            self._sync_subscription(data)
        elif event_type == "customer.subscription.deleted":
            self._sync_subscription(data, deleted=True)

        return Response({"received": True})

    def _sync_subscription(self, payload, deleted=False):
        customer_id = payload.get("customer")
        subscription_id = payload.get("id") or payload.get("subscription")
        if not customer_id:
            return

        try:
            subscription = Subscription.objects.get(stripe_customer_id=customer_id)
        except Subscription.DoesNotExist:
            return

        metadata = payload.get("metadata") or {}
        plan = metadata.get("plan") or subscription.plan
        status_value = Subscription.STATUS_CANCELED if deleted else (payload.get("status") or subscription.status)

        current_period_end = payload.get("current_period_end")
        dt_value = None
        if isinstance(current_period_end, int):
            dt_value = datetime.fromtimestamp(current_period_end, tz=timezone.utc)
        elif isinstance(current_period_end, str):
            dt_value = parse_datetime(current_period_end)

        subscription.stripe_subscription_id = subscription_id or subscription.stripe_subscription_id
        subscription.plan = plan
        subscription.status = status_value
        subscription.current_period_end = dt_value
        subscription.save()
