from rest_framework import serializers

from cors.models import Category, Document, Tag


class DocumentSerializer(serializers.ModelSerializer):
    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = Document
        fields = "__all__"


class DocumentLocalUploadSerializer(serializers.ModelSerializer):
    file = serializers.FileField(required=True)
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.none(), required=False, allow_null=True
    )
    tags = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.none(), many=True, required=False
    )

    class Meta:
        model = Document
        fields = [
            "title",
            "description",
            "file",
            "category",
            "tags",
            "date_issued",
            "date_expiration",
            "archived",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            self.fields["category"].queryset = Category.objects.filter(
                owner=user
            ) | Category.objects.filter(is_default=True)
            self.fields["tags"].queryset = Tag.objects.filter(owner=user) | Tag.objects.filter(
                is_default=True
            )

    def create(self, validated_data):
        tags = validated_data.pop("tags", [])
        uploaded_file = validated_data["file"]
        request = self.context["request"]

        if not validated_data.get("title"):
            validated_data["title"] = uploaded_file.name

        validated_data["owner"] = request.user
        validated_data["file_name"] = uploaded_file.name
        validated_data["mime_type"] = getattr(uploaded_file, "content_type", "") or ""
        validated_data["size"] = uploaded_file.size

        document = Document.objects.create(**validated_data)
        if tags:
            document.tags.set(tags)
        return document
