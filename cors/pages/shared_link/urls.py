from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import SharedLinkViewSet

router = DefaultRouter()
router.register("", SharedLinkViewSet, basename="shared-link")

urlpatterns = [
    path("", include(router.urls)),
]
