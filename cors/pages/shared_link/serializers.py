from rest_framework import serializers

from cors.models import SharedLink


class SharedLinkSerializer(serializers.ModelSerializer):
    creator = serializers.HiddenField(default=serializers.CurrentUserDefault())
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = SharedLink
        fields = [
            "id",
            "document",
            "creator",
            "token",
            "password",
            "password_required",
            "expires_at",
            "max_downloads",
            "download_count",
            "is_active",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "token",
            "download_count",
            "created_at",
            "password_required",
        ]

    def create(self, validated_data):
        raw_password = validated_data.pop("password", "")
        instance = super().create(validated_data)
        instance.set_password(raw_password)
        instance.save(update_fields=["password_required", "password_hash"])
        return instance

    def update(self, instance, validated_data):
        raw_password = validated_data.pop("password", None)
        instance = super().update(instance, validated_data)
        if raw_password is not None:
            instance.set_password(raw_password)
            instance.save(update_fields=["password_required", "password_hash"])
        return instance
