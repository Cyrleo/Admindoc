from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DocumentViewSet

router = DefaultRouter()
router.register("", DocumentViewSet, basename="document")
document_download = DocumentViewSet.as_view({"get": "download"})

urlpatterns = [
    path("download/<int:pk>/", document_download, name="document-download"),
    path("", include(router.urls)),
]
