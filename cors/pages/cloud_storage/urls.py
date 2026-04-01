from django.urls import path, include
from rest_framework.routers import DefaultRouter
from cors.pages.cloud_storage.views import (
    CloudStorageProviderViewSet,
    UserCloudStorageViewSet,
    CloudStorageActivityViewSet,
    DocumentFileCloudViewSet,
)
from cors.pages.cloud_storage.oauth_views import (
    initiate_oauth,
    oauth_callback_google,
    oauth_callback_onedrive,
    oauth_callback_dropbox,
)

router = DefaultRouter()
router.register(r'providers', CloudStorageProviderViewSet, basename='cloud-storage-providers')
router.register(r'connections', UserCloudStorageViewSet, basename='cloud-storage-connections')
router.register(r'activities', CloudStorageActivityViewSet, basename='cloud-storage-activities')
router.register(r'files', DocumentFileCloudViewSet, basename='cloud-storage-files')

urlpatterns = [
    path('', include(router.urls)),
    
    # OAuth endpoints
    path('oauth/initiate/', initiate_oauth, name='cloud-storage-oauth-initiate'),
    path('oauth/callback/google/', oauth_callback_google, name='cloud-storage-oauth-callback-google'),
    path('oauth/callback/onedrive/', oauth_callback_onedrive, name='cloud-storage-oauth-callback-onedrive'),
    path('oauth/callback/dropbox/', oauth_callback_dropbox, name='cloud-storage-oauth-callback-dropbox'),
]
