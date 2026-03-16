from drf_spectacular.utils import OpenApiResponse, OpenApiTypes, extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from cors.models import Reminder
from cors.tasks import send_reminder_email_task
from .serializers import ReminderSerializer


class ReminderViewSet(viewsets.ModelViewSet):
    serializer_class = ReminderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Reminder.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @extend_schema(
        responses={
            200: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Trigger reminder email delivery immediately.",
            )
        }
    )
    @action(detail=False, methods=["post"], url_path="trigger-now")
    def trigger_now(self, request):
        if not request.user.is_staff:
            return Response(
                {"detail": "Only staff users can trigger reminders manually."},
                status=status.HTTP_403_FORBIDDEN,
            )

        reminder_ids = request.data.get("reminder_ids") or []
        queryset = Reminder.objects.filter(enabled=True)
        if reminder_ids:
            queryset = queryset.filter(id__in=reminder_ids)

        dispatched = []
        for reminder in queryset:
            send_reminder_email_task.delay(reminder.id)
            dispatched.append(reminder.id)

        return Response({"triggered_reminder_ids": dispatched})
