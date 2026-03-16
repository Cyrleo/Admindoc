from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from cors.models import Reminder
from cors.tasks import enqueue_reminder_email
from .serializers import ReminderSerializer


class ReminderViewSet(viewsets.ModelViewSet):
    queryset = Reminder.objects.all()
    serializer_class = ReminderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):  # pyright: ignore[reportIncompatibleMethodOverride]
        return Reminder.objects.filter(owner=self.request.user).all()

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
            enqueue_reminder_email(reminder.pk)
            dispatched.append(reminder.pk)

        return Response({"triggered_reminder_ids": dispatched})
