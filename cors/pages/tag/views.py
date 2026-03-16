from django.db.models import Q
from rest_framework import generics, permissions, viewsets
from rest_framework.permissions import SAFE_METHODS

from cors.models import Tag
from .serializers import TagSerializer


class IsOwnerOrAdmin(permissions.BasePermission):
    """Seul le proprietaire ou un staff peut modifier/supprimer un tag."""

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if obj.is_default:
            return request.user and request.user.is_staff
        return obj.owner == request.user


class DefaultTagListView(generics.ListAPIView):
    """
    GET /api/tags/defaults/
    Retourne uniquement les tags par defaut, accessible sans authentification.
    """

    serializer_class = TagSerializer
    permission_classes = [permissions.AllowAny]
    queryset = Tag.objects.filter(is_default=True)


class TagViewSet(viewsets.ModelViewSet):
    serializer_class = TagSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), IsOwnerOrAdmin()]

    def get_queryset(self):
        if self.request.user.is_authenticated:
            return Tag.objects.filter(
                Q(is_default=True) | Q(owner=self.request.user)
            )
        return Tag.objects.filter(is_default=True)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user, is_default=False)
