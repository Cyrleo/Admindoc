# pyright: reportIncompatibleVariableOverride=false

"""Serializers de l'API admin.

Ces serializers exposent des vues metier orientees back-office:
- informations enrichies (email proprietaire, nom connexion, etc.)
- champs sensibles verrouilles en lecture seule quand necessaire
"""

from accounts.models import User
from rest_framework import serializers

from cors.pages.admin_api.permissions import ADMIN_ROLE_NAMES

from cors.models import (
    AuditLog,
    Category,
    CloudStorageActivity,
    CloudStorageProvider,
    Document,
    DocumentFile,
    Reminder,
    ReminderLog,
    Subscription,
    Tag,
    UserCloudStorage,
)


class AdminUserSerializer(serializers.ModelSerializer):
    """Representation admin d'un utilisateur.

    Inclut la liste des roles admin derives des groupes Django.
    """

    admin_roles = serializers.SerializerMethodField()

    def get_admin_roles(self, obj):
        # Un utilisateur peut cumuler plusieurs roles admin.
        names = obj.groups.values_list("name", flat=True)
        return sorted([name for name in names if name in ADMIN_ROLE_NAMES])

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "is_staff",
            "is_superuser",
            "is_active",
            "is_verified",
            "date_joined",
            "last_login",
            "admin_roles",
        ]
        read_only_fields = ["id", "date_joined", "last_login"]


class AdminDocumentSerializer(serializers.ModelSerializer):
    """Serializer admin pour la supervision globale des documents."""
    owner_email = serializers.EmailField(source="owner.email", read_only=True)

    class Meta:
        model = Document
        fields = [
            "id",
            "owner",
            "owner_email",
            "title",
            "description",
            "category",
            "tags",
            "date_issued",
            "date_expiration",
            "archived",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class AdminDefaultCategorySerializer(serializers.ModelSerializer):
    """Serializer admin des categories par defaut (globales)."""
    class Meta:
        model = Category
        fields = ["id", "name", "icon", "is_default", "created_at", "updated_at"]
        read_only_fields = ["id", "is_default", "created_at", "updated_at"]


class AdminDefaultTagSerializer(serializers.ModelSerializer):
    """Serializer admin des tags par defaut (globaux)."""
    class Meta:
        model = Tag
        fields = ["id", "name", "color", "is_default", "created_at"]
        read_only_fields = ["id", "is_default", "created_at"]


class AdminReminderSerializer(serializers.ModelSerializer):
    """Serializer admin des rappels et de leur contexte utilisateur/document."""
    owner_email = serializers.EmailField(source="owner.email", read_only=True)
    document_title = serializers.CharField(source="document.title", read_only=True)

    class Meta:
        model = Reminder
        fields = [
            "id",
            "owner",
            "owner_email",
            "document",
            "document_title",
            "days_before",
            "method",
            "enabled",
            "next_run",
            "last_sent",
            "created_at",
        ]


class AdminReminderLogSerializer(serializers.ModelSerializer):
    """Serializer des logs d'envoi de rappels."""
    reminder_id = serializers.IntegerField(source="reminder.id", read_only=True)

    class Meta:
        model = ReminderLog
        fields = [
            "id",
            "recipient",
            "reminder_id",
            "status",
            "sent_at",
            "error_message",
            "created_at",
        ]


class AdminAuditLogSerializer(serializers.ModelSerializer):
    """Serializer des traces d'audit."""
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "user",
            "user_email",
            "action",
            "target_type",
            "target_id",
            "meta",
            "timestamp",
        ]


class AdminSubscriptionSerializer(serializers.ModelSerializer):
    """Serializer admin des abonnements."""
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id",
            "user",
            "user_email",
            "plan",
            "status",
            "stripe_customer_id",
            "stripe_subscription_id",
            "current_period_end",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class AdminCloudStorageProviderSerializer(serializers.ModelSerializer):
    """Serializer admin des fournisseurs cloud supportes."""
    class Meta:
        model = CloudStorageProvider
        fields = [
            "id",
            "code",
            "name",
            "icon",
            "is_active",
            "requires_oauth",
            "api_base_url",
            "updated_at",
        ]


class AdminCloudConnectionSerializer(serializers.ModelSerializer):
    """Serializer admin des connexions cloud des utilisateurs."""
    user_email = serializers.EmailField(source="user.email", read_only=True)
    provider_code = serializers.CharField(source="provider.code", read_only=True)

    class Meta:
        model = UserCloudStorage
        fields = [
            "id",
            "user",
            "user_email",
            "provider",
            "provider_code",
            "display_name",
            "cloud_account_email",
            "is_default",
            "is_active",
            "total_space",
            "used_space",
            "last_sync",
            "created_at",
            "updated_at",
        ]


class AdminCloudActivitySerializer(serializers.ModelSerializer):
    """Serializer admin de l'activite cloud."""
    connection_name = serializers.CharField(source="user_storage.display_name", read_only=True)

    class Meta:
        model = CloudStorageActivity
        fields = [
            "id",
            "user_storage",
            "connection_name",
            "action",
            "details",
            "metadata",
            "timestamp",
        ]


class AdminDocumentFileSerializer(serializers.ModelSerializer):
    """Serializer admin des fichiers attaches aux documents."""
    document_title = serializers.CharField(source="document.title", read_only=True)

    class Meta:
        model = DocumentFile
        fields = [
            "id",
            "document",
            "document_title",
            "file_name",
            "mime_type",
            "size",
            "storage_type",
            "sync_status",
            "uploaded_at",
        ]
