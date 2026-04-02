from rest_framework import serializers
from rest_framework.reverse import reverse

from cors.models import Category, Document, DocumentFile, Tag


class DocumentFileSerializer(serializers.ModelSerializer):
    """Serializer for individual document files."""
    download_url = serializers.SerializerMethodField()

    def get_download_url(self, obj):
        request = self.context.get("request")
        return reverse("document-download-file", kwargs={"file_id": obj.pk}, request=request)
    
    class Meta:
        model = DocumentFile
        fields = [
            'id',
            'file',
            'file_name',
            'mime_type',
            'size',
            'is_primary',
            'uploaded_at',
            'created_at',
            'updated_at',
            'download_url',
        ]
        read_only_fields = ['id', 'uploaded_at', 'created_at', 'updated_at', 'download_url']


class DocumentSerializer(serializers.ModelSerializer):
    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())
    files = DocumentFileSerializer(many=True, read_only=True)
    download_url = serializers.SerializerMethodField()

    def get_download_url(self, obj):
        request = self.context.get("request")
        return reverse("document-download", kwargs={"pk": obj.pk}, request=request)

    class Meta:
        model = Document
        fields = [
            'id',
            'owner',
            'files',
            'download_url',
            'title',
            'description',
            'file',
            'file_name',
            'mime_type',
            'size',
            'category',
            'tags',
            'date_issued',
            'date_expiration',
            'is_encrypted',
            'checksum',
            'created_at',
            'updated_at',
            'archived',
        ]
        read_only_fields = ['id', 'files', 'download_url', 'created_at', 'updated_at']


class DocumentLocalUploadSerializer(serializers.ModelSerializer):
    """
    Serializer for uploading documents with multiple files.
    Accepts 'files' (multiple) instead of 'file' (single).
    """
    files = serializers.ListField(
        child=serializers.FileField(),
        required=True,
        help_text="List of files to upload (images, PDFs, Word, Excel, etc.)"
    )
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), required=False, allow_null=True
    )
    tags = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(), many=True, required=False
    )

    class Meta:
        model = Document
        fields = [
            "title",
            "description",
            "files",
            "category",
            "tags",
            "date_issued",
            "date_expiration",
            "archived",
        ]

    def validate_files(self, files):
        """Validate uploaded files."""
        if not files:
            raise serializers.ValidationError("At least one file is required.")
        
        # Optional: Add file size limit per file (e.g., 50MB)
        max_file_size = 50 * 1024 * 1024  # 50MB
        for uploaded_file in files:
            if uploaded_file.size > max_file_size:
                raise serializers.ValidationError(
                    f"File {uploaded_file.name} exceeds maximum size of 50MB."
                )
        
        return files

    def create(self, validated_data):
        tags = validated_data.pop("tags", [])
        uploaded_files = validated_data.pop("files")
        request = self.context["request"]

        # Use first file's name as default title if not provided
        if not validated_data.get("title"):
            validated_data["title"] = uploaded_files[0].name

        validated_data["owner"] = request.user
        
        # Remove old deprecated fields from creation
        validated_data.pop("file", None)
        validated_data.pop("file_name", None)
        validated_data.pop("mime_type", None)
        validated_data.pop("size", None)

        # Create the document
        document = Document.objects.create(**validated_data)
        
        if tags:
            document.tags.set(tags)
        
        # Create DocumentFile entries for each uploaded file
        for index, uploaded_file in enumerate(uploaded_files):
            DocumentFile.objects.create(
                document=document,
                file=uploaded_file,
                file_name=uploaded_file.name,
                mime_type=getattr(uploaded_file, "content_type", "") or "",
                size=uploaded_file.size,
                is_primary=(index == 0),  # First file is primary
            )
        
        return document
