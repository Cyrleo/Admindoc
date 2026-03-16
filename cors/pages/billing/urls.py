from django.urls import path

from .views import CreateCheckoutSessionView, StripeWebhookView

urlpatterns = [
    path("create-checkout-session/", CreateCheckoutSessionView.as_view(), name="billing-create-checkout-session"),
    path("webhooks/stripe/", StripeWebhookView.as_view(), name="stripe-webhook-api"),
]
