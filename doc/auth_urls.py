from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from djoser.views import UserViewSet
from djoser.social.views import ProviderAuthView


urlpatterns = [
    path("signup/", UserViewSet.as_view({"post": "create"}), name="signup"),
    path("login/", TokenObtainPairView.as_view(), name="login"),
    path("refresh/", TokenRefreshView.as_view(), name="refresh"),
    path("google/", ProviderAuthView.as_view(), {"provider": "google-oauth2"}, name="google-auth"),
    path("github/", ProviderAuthView.as_view(), {"provider": "github"}, name="github-auth"),
    path("", include("djoser.social.urls")),
    path("", include("djoser.urls")),
    path("", include("djoser.urls.jwt")),
]
