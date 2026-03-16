from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet, DefaultCategoryListView

router = DefaultRouter()
router.register("", CategoryViewSet, basename="category")

urlpatterns = [
    # GET /api/categories/defaults/ — accessible sans authentification
    path("defaults/", DefaultCategoryListView.as_view(), name="category-defaults"),
    path("", include(router.urls)),
]
