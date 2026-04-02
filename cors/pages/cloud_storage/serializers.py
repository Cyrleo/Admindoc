from rest_framework import serializers
from cors.models import CloudStorageProvider, UserCloudStorage, CloudStorageActivity, DocumentFile


class CloudStorageProviderSerializer(serializers.ModelSerializer):
    """
    Serializer pour les providers de stockage cloud disponibles.
    """
    class Meta:
        model = CloudStorageProvider
        fields = [
            'id',
            'code',
            'name',
            'icon',
            'is_active',
            'requires_oauth',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class UserCloudStorageSerializer(serializers.ModelSerializer):
    """
    Serializer pour les connexions cloud storage d'un utilisateur.
    """
    provider = CloudStorageProviderSerializer(read_only=True)
    provider_id = serializers.PrimaryKeyRelatedField(
        queryset=CloudStorageProvider.objects.filter(is_active=True),
        source='provider',
        write_only=True
    )
    available_space = serializers.SerializerMethodField()
    
    class Meta:
        model = UserCloudStorage
        fields = [
            'id',
            'provider',
            'provider_id',
            'cloud_account_email',
            'cloud_account_name',
            'display_name',
            'is_default',
            'is_active',
            'total_space',
            'used_space',
            'available_space',
            'last_sync',
            'base_folder',
            'auto_organize',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'cloud_account_email',
            'cloud_account_name',
            'total_space',
            'used_space',
            'last_sync',
            'created_at',
            'updated_at',
        ]
    
    def get_available_space(self, obj):
        """Calcule l'espace disponible."""
        return obj.available_space
    
    def create(self, validated_data):
        # Ajouter l'utilisateur courant
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class CloudStorageActivitySerializer(serializers.ModelSerializer):
    """
    Serializer pour l'historique des activités cloud.
    """
    user_storage_display = serializers.CharField(source='user_storage.display_name', read_only=True)
    document_file_name = serializers.CharField(source='document_file.file_name', read_only=True)
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    
    class Meta:
        model = CloudStorageActivity
        fields = [
            'id',
            'user_storage',
            'user_storage_display',
            'action',
            'action_display',
            'document_file',
            'document_file_name',
            'details',
            'metadata',
            'timestamp',
        ]
        read_only_fields = ['id', 'timestamp']


class CloudFileUploadSerializer(serializers.Serializer):
    """
    Serializer pour l'upload de fichiers vers le cloud storage.
    """
    files = serializers.ListField(
        child=serializers.FileField(),
        required=True,
        help_text="Liste de fichiers à uploader"
    )
    storage_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="ID du UserCloudStorage (optionnel, défaut=local)"
    )
    storage_type = serializers.ChoiceField(
        choices=[('local', 'Local'), ('cloud', 'Cloud')],
        default='local',
        help_text="Type de stockage"
    )
    
    def validate_storage_id(self, value):
        """Valide que le storage_id existe et appartient à l'utilisateur."""
        if value:
            user = self.context['request'].user
            try:
                storage = UserCloudStorage.objects.get(id=value, user=user, is_active=True)
                return storage
            except UserCloudStorage.DoesNotExist:
                raise serializers.ValidationError(
                    f"Cloud storage with ID {value} not found or inactive."
                )
        return None


class DocumentFileMoveSerializer(serializers.Serializer):
    """
    Serializer pour déplacer un fichier entre storages.
    """
    target_storage_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="ID du storage cible (null=local)"
    )
    delete_source = serializers.BooleanField(
        default=False,
        help_text="Supprimer le fichier source après migration?"
    )
    
    def validate_target_storage_id(self, value):
        """Valide le storage cible."""
        if value:
            user = self.context['request'].user
            try:
                storage = UserCloudStorage.objects.get(id=value, user=user, is_active=True)
                return storage
            except UserCloudStorage.DoesNotExist:
                raise serializers.ValidationError(
                    f"Cloud storage with ID {value} not found or inactive."
                )
        return None
