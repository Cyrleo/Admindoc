from rest_framework import serializers

from cors.models import Reminder


class ReminderSerializer(serializers.ModelSerializer):
    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = Reminder
        fields = "__all__"
