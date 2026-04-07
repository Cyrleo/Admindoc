from pathlib import Path
from tempfile import SpooledTemporaryFile
import zipfile
from io import BytesIO

from django.db.models import Q
from django.http import FileResponse
from django.utils.text import slugify
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from cors.models import AuditLog, Document, DocumentFile
from .filters import DocumentFilter
from .serializers import DocumentLocalUploadSerializer, DocumentSerializer
from cors.storage.factory import CloudStorageFactory
from cors.storage.token_manager import TokenManager


def _download_name(value, fallback):
    name = value or fallback
    return Path(name).name


def _read_document_file_content(document_file):
    if document_file.file and document_file.file.name:
        with document_file.file.open("rb") as file_handle:
            return file_handle.read()

    if (
        document_file.storage_type == DocumentFile.STORAGE_CLOUD
        and document_file.cloud_storage
        and document_file.cloud_file_id
    ):
        if not TokenManager.ensure_valid_token(document_file.cloud_storage):
            raise PermissionError("Failed to authenticate with cloud storage")

        backend = CloudStorageFactory.get_backend(document_file.cloud_storage)
        return backend.download_file(document_file.cloud_file_id)

    raise FileNotFoundError("No downloadable content found for this document file")


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
        # Check if this is a swagger fake view for schema generation
        if getattr(self, "swagger_fake_view", False):
            return Document.objects.none()
        
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
                response=OpenApiTypes.BINARY,
                description="Returns a ZIP archive containing all files for the document.",
            )
        }
    )
    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, pk=None):
        """
        Download all files for a document as a ZIP archive.
        For backward compatibility, also checks the deprecated 'file' field.
        """
        document = self.get_object()

        document_files = list(document.files.all())
        if not document_files and document.file:
            document_files = [document]

        if not document_files:
            return Response(
                {"detail": "No file associated with this document."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        zip_buffer = SpooledTemporaryFile(max_size=10 * 1024 * 1024, mode="w+b")
        archive_root = slugify(document.title) or f"document-{document.pk}"
        zip_filename = f"{archive_root}-{document.pk}.zip"

        with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            for index, item in enumerate(document_files, start=1):
                if isinstance(item, Document):
                    file_field = item.file
                    file_name = _download_name(item.file_name, item.file.name)
                else:
                    file_field = item.file
                    file_name = _download_name(item.file_name, item.file.name)

                archive_name = f"{index:02d}_{file_name}"
                if file_field and file_field.name:
                    with file_field.open("rb") as file_handle:
                        zip_file.writestr(archive_name, file_handle.read())
                else:
                    content = _read_document_file_content(item)
                    zip_file.writestr(archive_name, content)

        zip_buffer.seek(0)

        AuditLog.objects.create(
            user=request.user,
            action="download_document_zip",
            target_type="Document",
            target_id=str(document.pk),
            meta={
                "file_count": len(document_files),
                "zip_name": zip_filename,
                "document_id": str(document.pk),
            },
        )

        response = FileResponse(zip_buffer, as_attachment=True, filename=zip_filename)
        response["Content-Type"] = "application/zip"
        return response
    
    @extend_schema(
        responses={
            200: OpenApiResponse(
                response=OpenApiTypes.BINARY,
                description="Returns the requested document file.",
            )
        }
    )
    @action(detail=False, methods=["get"], url_path=r"files/(?P<file_id>[0-9a-fA-F-]{36})/download")
    def download_file(self, request, file_id=None):
        """
        Download a specific file by its ID.
        Only allows downloading files from documents owned by the user.
        """
        try:
            document_file = DocumentFile.objects.select_related('document').get(
                id=file_id,
                document__owner=request.user
            )
        except DocumentFile.DoesNotExist:
            return Response(
                {"detail": "File not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        AuditLog.objects.create(
            user=request.user,
            action="download_document_file",
            target_type="DocumentFile",
            target_id=str(document_file.pk),
            meta={
                "file_name": document_file.file_name,
                "document_id": str(document_file.document.pk),
            },
        )

        file_name = _download_name(document_file.file_name, document_file.file.name)
        try:
            if document_file.file and document_file.file.name:
                file_handle = document_file.file.open("rb")
                response = FileResponse(file_handle, as_attachment=True, filename=file_name)
            else:
                content = _read_document_file_content(document_file)
                response = FileResponse(BytesIO(content), as_attachment=True, filename=file_name)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        except FileNotFoundError:
            return Response(
                {"detail": "No file associated with this document file."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return response

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
