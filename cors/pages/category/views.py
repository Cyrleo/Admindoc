from django.db.models import Q
from rest_framework import generics, permissions, viewsets
from rest_framework.permissions import SAFE_METHODS

from cors.models import Category
from .serializers import CategorySerializer


class DefaultCategoryListView(generics.ListAPIView):
    """
    GET /api/categories/defaults/
    Retourne uniquement les catégories par défaut — aucune authentification requise.
    """
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]
    queryset = Category.objects.filter(is_default=True)


class IsOwnerOrAdmin(permissions.BasePermission):
    """Seul le propriétaire ou un staff peut modifier/supprimer une catégorie."""

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if obj.is_default:
            return request.user and request.user.is_staff
        return obj.owner == request.user


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            # Lecture publique : catégories par défaut visibles sans auth
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), IsOwnerOrAdmin()]

    def get_queryset(self):
        if self.request.user.is_authenticated:
            # Catégories par défaut + catégories personnelles de l'utilisateur
            return Category.objects.filter(
                Q(is_default=True) | Q(owner=self.request.user)
            )
        # Non authentifié : catégories par défaut uniquement
        return Category.objects.filter(is_default=True)

    def perform_create(self, serializer):
        # Les créations utilisateur sont toujours des catégories personnelles
        serializer.save(owner=self.request.user, is_default=False)
