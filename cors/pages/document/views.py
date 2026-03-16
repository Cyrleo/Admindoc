from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from cors.models import AuditLog, Document
from .filters import DocumentFilter
from .serializers import DocumentLocalUploadSerializer, DocumentSerializer


class DocumentViewSet(viewsets.ModelViewSet):
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_class = DocumentFilter
    search_fields = ["title", "description", "tags__name", "category__name"]
    ordering_fields = ["created_at", "updated_at", "date_expiration", "title", "size"]
    ordering = ["-created_at"]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="category",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Filter by category id(s). Ex: 1 or 1,2",
            ),
            OpenApiParameter(
                name="categories",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Alias of category. Ex: 1,2",
            ),
            OpenApiParameter(
                name="tag",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Filter by tag id(s). Ex: 3 or 3,4",
            ),
            OpenApiParameter(
                name="tags",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Alias of tag. Ex: 3,4",
            ),
            OpenApiParameter(
                name="expiration_from",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="Expiration start date (YYYY-MM-DD)",
            ),
            OpenApiParameter(
                name="expiration_to",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="Expiration end date (YYYY-MM-DD)",
            ),
            OpenApiParameter(
                name="expiration_month",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Expiration month (YYYY-MM)",
            ),
            OpenApiParameter(
                name="expires_in_days",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Documents expiring in the next N days",
            ),
            OpenApiParameter(
                name="expired",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description="true => already expired documents",
            ),
            OpenApiParameter(
                name="no_expiration",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description="true => documents without expiration date",
            ),
            OpenApiParameter(
                name="search",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Full-text style search over title, description, tags and category",
            ),
            OpenApiParameter(
                name="q",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Alias for text search (ILIKE on title/tags/category)",
            ),
            OpenApiParameter(
                name="ordering",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Sort fields: created_at, updated_at, date_expiration, title, size. Prefix with '-' for DESC.",
            ),
            OpenApiParameter(
                name="page",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Paginated page number",
            ),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        queryset = Document.objects.filter(owner=self.request.user)

        # Free text query alias for ILIKE-like matching on PostgreSQL.
        text_query = self.request.query_params.get("q")
        if text_query:
            text_query = text_query.strip()
            queryset = queryset.filter(
                Q(title__icontains=text_query)
                | Q(description__icontains=text_query)
                | Q(tags__name__icontains=text_query)
                | Q(category__name__icontains=text_query)
            )

        return queryset.distinct()

    @extend_schema(
        responses={
            200: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Returns a temporary download URL for the document.",
            )
        }
    )
    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, pk=None):
        document = self.get_object()

        if not document.file:
            return Response(
                {"detail": "No file associated with this document."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # For storages supporting temporary signed URLs (e.g. S3Boto3Storage)
            download_url = document.file.storage.url(document.file.name, expire=3600)
        except TypeError:
            # Fallback for storages without `expire` argument
            download_url = document.file.storage.url(document.file.name)

        if download_url.startswith("/"):
            download_url = request.build_absolute_uri(download_url)

        AuditLog.objects.create(
            user=request.user,
            action="download_document",
            target_type="Document",
            target_id=str(document.pk),
            meta={
                "file_name": document.file_name or document.file.name,
                "document_id": document.pk,
            },
        )

        return Response({"download_url": download_url})

    @extend_schema(
        request=DocumentLocalUploadSerializer,
        responses={201: DocumentSerializer},
        description="Dev/local upload endpoint. Accepts multipart form-data, stores the file locally, and creates the document.",
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="upload-local",
        parser_classes=[MultiPartParser, FormParser],
    )
    def upload_local(self, request):
        serializer = DocumentLocalUploadSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        document = serializer.save()
        return Response(DocumentSerializer(document, context={"request": request}).data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
