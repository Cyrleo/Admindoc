from rest_framework import permissions, viewsets

from cors.models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogViewSet(viewsets.ModelViewSet):
    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Check if this is a swagger fake view for schema generation
        if getattr(self, "swagger_fake_view", False):
            return AuditLog.objects.none()
        
        return AuditLog.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
