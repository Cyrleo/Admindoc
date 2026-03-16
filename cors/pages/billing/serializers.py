from rest_framework import serializers


class CheckoutSessionSerializer(serializers.Serializer):
    price_id = serializers.CharField()
    success_url = serializers.URLField()
    cancel_url = serializers.URLField()
    plan = serializers.CharField(required=False, allow_blank=True)
