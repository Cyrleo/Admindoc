from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from cors.models import AuditLog, SharedLink
from .serializers import SharedLinkSerializer


class SharedLinkViewSet(viewsets.ModelViewSet):
    serializer_class = SharedLinkSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return SharedLink.objects.filter(creator=self.request.user)

    def perform_create(self, serializer):
        serializer.save(creator=self.request.user)


class PublicSharedLinkView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="password",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Password required for protected shared links",
                required=False,
            )
        ],
        responses={
            200: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Returns a temporary download URL for the shared document.",
            )
        },
    )
    def get(self, request, token):
        try:
            shared_link = SharedLink.objects.select_related("document").get(token=token)
        except SharedLink.DoesNotExist:
            return Response({"detail": "Shared link not found."}, status=status.HTTP_404_NOT_FOUND)

        if shared_link.is_expired():
            return Response({"detail": "Shared link is expired or inactive."}, status=status.HTTP_410_GONE)

        raw_password = request.query_params.get("password", "")
        if shared_link.password_required and not shared_link.check_password(raw_password):
            return Response({"detail": "Invalid or missing password."}, status=status.HTTP_403_FORBIDDEN)

        shared_link.increment_download()

        document = shared_link.document
        try:
            download_url = document.file.storage.url(document.file.name, expire=3600)
        except TypeError:
            download_url = document.file.storage.url(document.file.name)

        if download_url.startswith("/"):
            download_url = request.build_absolute_uri(download_url)

        AuditLog.objects.create(
            user=None,
            action="download_shared_link",
            target_type="SharedLink",
            target_id=str(shared_link.pk),
            meta={
                "document_id": document.pk,
                "download_count": shared_link.download_count,
                "token": str(shared_link.token),
            },
        )

        return Response(
            {
                "download_url": download_url,
                "document_id": document.pk,
                "expires_at": shared_link.expires_at,
                "remaining_downloads": (
                    None
                    if shared_link.max_downloads is None
                    else max(shared_link.max_downloads - shared_link.download_count, 0)
                ),
            }
        )
