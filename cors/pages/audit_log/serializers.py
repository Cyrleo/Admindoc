from rest_framework import serializers

from cors.models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = AuditLog
        fields = "__all__"
