from django.urls import path, include
from rest_framework.routers import DefaultRouter
from cors.pages.cloud_storage.views import (
    CloudStorageProviderViewSet,
    UserCloudStorageViewSet,
    CloudStorageActivityViewSet,
    DocumentFileCloudViewSet,
)

router = DefaultRouter()
router.register(r'providers', CloudStorageProviderViewSet, basename='cloud-storage-providers')
router.register(r'connections', UserCloudStorageViewSet, basename='cloud-storage-connections')
router.register(r'activities', CloudStorageActivityViewSet, basename='cloud-storage-activities')
router.register(r'files', DocumentFileCloudViewSet, basename='cloud-storage-files')

urlpatterns = [
    path('', include(router.urls)),
]
