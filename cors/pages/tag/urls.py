from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DefaultTagListView, TagViewSet

router = DefaultRouter()
router.register("", TagViewSet, basename="tag")

urlpatterns = [
    path("default/", DefaultTagListView.as_view(), name="tag-default"),
    path("defaults/", DefaultTagListView.as_view(), name="tag-defaults"),
    path("", include(router.urls)),
]
