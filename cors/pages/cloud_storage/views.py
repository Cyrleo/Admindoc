from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone

from cors.models import CloudStorageProvider, UserCloudStorage, CloudStorageActivity, DocumentFile
from cors.pages.cloud_storage.serializers import (
    CloudStorageProviderSerializer,
    UserCloudStorageSerializer,
    CloudStorageActivitySerializer,
    DocumentFileMoveSerializer,
)
from cors.storage.factory import CloudStorageFactory
from cors.storage.token_manager import TokenManager
import logging

logger = logging.getLogger(__name__)


class CloudStorageProviderViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoints pour lister les providers de stockage cloud disponibles.
    
    list: Liste tous les providers actifs
    retrieve: Détails d'un provider spécifique
    """
    queryset = CloudStorageProvider.objects.filter(is_active=True)
    serializer_class = CloudStorageProviderSerializer
    permission_classes = [IsAuthenticated]


class UserCloudStorageViewSet(viewsets.ModelViewSet):
    """
    API endpoints pour gérer les connexions cloud storage de l'utilisateur.
    
    list: Liste les connexions de l'utilisateur
    retrieve: Détails d'une connexion
    create: Crée une nouvelle connexion (sera complétée par OAuth)
    update/partial_update: Modifie une connexion
    destroy: Supprime une connexion
    
    Actions personnalisées:
    - connect: Démarre le flow OAuth
    - disconnect: Déconnecte un storage
    - sync_quota: Synchronise les informations de quota
    - set_default: Définit un storage comme défaut
    - test_connection: Teste la connexion
    """
    serializer_class = UserCloudStorageSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filtre les connexions de l'utilisateur courant."""
        return UserCloudStorage.objects.filter(
            user=self.request.user
        ).select_related('provider')
    
    def perform_create(self, serializer):
        """Crée une connexion pour l'utilisateur courant."""
        serializer.save(user=self.request.user)
    
    @action(detail=False, methods=['post'])
    def connect(self, request):
        """
        Initie le flow OAuth pour connecter un provider.
        
        POST /api/cloud-storage/connections/connect/
        Body: { "provider_id": 1, "display_name": "Mon Google Drive" }
        
        Returns: OAuth URL pour rediriger l'utilisateur
        """
        provider_id = request.data.get('provider_id')
        display_name = request.data.get('display_name', 'My Cloud Storage')
        
        if not provider_id:
            return Response(
                {'error': 'provider_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        provider = get_object_or_404(CloudStorageProvider, id=provider_id, is_active=True)
        
        # TODO: Implémenter la génération de l'URL OAuth selon le provider
        # Pour l'instant, on retourne un placeholder
        oauth_url = f"https://oauth.example.com/{provider.code}/authorize"
        
        return Response({
            'provider': CloudStorageProviderSerializer(provider).data,
            'oauth_url': oauth_url,
            'message': 'Redirect user to oauth_url to complete authentication'
        })
    
    @action(detail=True, methods=['post'])
    def disconnect(self, request, pk=None):
        """
        Déconnecte un cloud storage.
        
        POST /api/cloud-storage/connections/{id}/disconnect/
        """
        user_storage = self.get_object()
        
        # Révoquer le token
        TokenManager.revoke_token(user_storage)
        
        # Logger l'activité
        CloudStorageActivity.objects.create(
            user_storage=user_storage,
            action='disconnect',
            details='Storage disconnected by user'
        )
        
        return Response({
            'message': f'{user_storage.display_name} disconnected successfully'
        })
    
    @action(detail=True, methods=['post'])
    def sync_quota(self, request, pk=None):
        """
        Synchronise les informations de quota avec le provider.
        
        POST /api/cloud-storage/connections/{id}/sync_quota/
        """
        user_storage = self.get_object()
        
        try:
            # Vérifier/rafraîchir le token
            if not TokenManager.ensure_valid_token(user_storage):
                return Response(
                    {'error': 'Failed to refresh token. Please reconnect.'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            # Récupérer les infos de quota via le backend
            backend = CloudStorageFactory.get_backend(user_storage)
            quota_info = backend.get_quota_info()
            
            # Mettre à jour le modèle
            user_storage.total_space = quota_info.get('total_space', 0)
            user_storage.used_space = quota_info.get('used_space', 0)
            user_storage.last_sync = timezone.now()
            user_storage.save()
            
            # Logger l'activité
            CloudStorageActivity.objects.create(
                user_storage=user_storage,
                action='sync',
                details='Quota information synchronized',
                metadata=quota_info
            )
            
            return Response({
                'message': 'Quota synchronized successfully',
                'quota': quota_info
            })
            
        except Exception as e:
            logger.error(f"Quota sync failed for {user_storage}: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        """
        Définit ce storage comme défaut pour l'utilisateur.
        
        POST /api/cloud-storage/connections/{id}/set_default/
        """
        user_storage = self.get_object()
        
        # Retirer le flag default des autres storages
        UserCloudStorage.objects.filter(
            user=request.user,
            is_default=True
        ).update(is_default=False)
        
        # Définir celui-ci comme default
        user_storage.is_default = True
        user_storage.save()
        
        return Response({
            'message': f'{user_storage.display_name} is now your default storage'
        })
    
    @action(detail=True, methods=['get'])
    def test_connection(self, request, pk=None):
        """
        Teste la connexion au cloud storage.
        
        GET /api/cloud-storage/connections/{id}/test_connection/
        """
        user_storage = self.get_object()
        
        try:
            # Vérifier le token
            if not TokenManager.ensure_valid_token(user_storage):
                return Response(
                    {'status': 'error', 'message': 'Invalid or expired token'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            # Tester avec une requête simple (liste des fichiers)
            backend = CloudStorageFactory.get_backend(user_storage)
            backend.list_files()
            
            return Response({
                'status': 'success',
                'message': 'Connection is active and working'
            })
            
        except Exception as e:
            logger.error(f"Connection test failed for {user_storage}: {e}")
            return Response(
                {'status': 'error', 'message': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CloudStorageActivityViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoints pour consulter l'historique des activités cloud.
    
    list: Liste les activités de l'utilisateur
    retrieve: Détails d'une activité
    """
    serializer_class = CloudStorageActivitySerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filtre les activités de l'utilisateur courant."""
        return CloudStorageActivity.objects.filter(
            user_storage__user=self.request.user
        ).select_related('user_storage', 'document_file').order_by('-timestamp')


class DocumentFileCloudViewSet(viewsets.ViewSet):
    """
    API endpoints pour gérer les fichiers entre local et cloud.
    
    Actions:
    - move_to_cloud: Déplace un fichier local vers le cloud
    - move_to_local: Rapatrie un fichier cloud en local
    """
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['post'], url_path='move-to-cloud/(?P<file_id>[^/.]+)')
    def move_to_cloud(self, request, file_id=None):
        """
        Déplace un fichier local vers un cloud storage.
        
        POST /api/documents/files/move-to-cloud/{file_id}/
        Body: {
            "target_storage_id": 1,
            "delete_source": false
        }
        """
        # Récupérer le fichier
        document_file = get_object_or_404(
            DocumentFile,
            id=file_id,
            document__user=request.user,
            storage_type='local'
        )
        
        serializer = DocumentFileMoveSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        target_storage = serializer.validated_data.get('target_storage_id')
        delete_source = serializer.validated_data.get('delete_source', False)
        
        if not target_storage:
            return Response(
                {'error': 'target_storage_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Vérifier le token
            if not TokenManager.ensure_valid_token(target_storage):
                return Response(
                    {'error': 'Failed to authenticate with cloud storage'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            # Upload vers le cloud
            document_file.sync_status = 'uploading'
            document_file.save()
            
            backend = CloudStorageFactory.get_backend(target_storage)
            
            # Construire le chemin
            path = f"{target_storage.base_folder}/{document_file.document.document_type.name}/"
            
            # Upload
            with document_file.file.open('rb') as f:
                result = backend.upload_file(
                    file=f,
                    path=path,
                    metadata={
                        'name': document_file.file_name,
                        'mime_type': document_file.file_type,
                    }
                )
            
            # Mettre à jour le DocumentFile
            document_file.storage_type = 'cloud'
            document_file.cloud_storage = target_storage
            document_file.cloud_file_id = result['file_id']
            document_file.cloud_file_path = result.get('path', path)
            document_file.cloud_url = result.get('url')
            document_file.cloud_metadata = result.get('metadata', {})
            document_file.sync_status = 'synced'
            document_file.last_synced = timezone.now()
            
            # Supprimer le fichier local si demandé
            if delete_source:
                document_file.file.delete(save=False)
            
            document_file.save()
            
            # Logger l'activité
            CloudStorageActivity.objects.create(
                user_storage=target_storage,
                action='upload',
                document_file=document_file,
                details=f'File moved from local to {target_storage.display_name}'
            )
            
            return Response({
                'message': 'File moved to cloud successfully',
                'file': {
                    'id': document_file.id,
                    'storage_type': document_file.storage_type,
                    'cloud_storage': target_storage.display_name,
                    'sync_status': document_file.sync_status,
                }
            })
            
        except Exception as e:
            logger.error(f"Failed to move file {file_id} to cloud: {e}")
            document_file.sync_status = 'error'
            document_file.sync_error = str(e)
            document_file.save()
            
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], url_path='move-to-local/(?P<file_id>[^/.]+)')
    def move_to_local(self, request, file_id=None):
        """
        Rapatrie un fichier cloud en local.
        
        POST /api/documents/files/move-to-local/{file_id}/
        Body: { "delete_source": false }
        """
        # Récupérer le fichier
        document_file = get_object_or_404(
            DocumentFile,
            id=file_id,
            document__user=request.user,
            storage_type='cloud'
        )
        
        delete_source = request.data.get('delete_source', False)
        cloud_storage = document_file.cloud_storage
        
        try:
            # Vérifier le token
            if not TokenManager.ensure_valid_token(cloud_storage):
                return Response(
                    {'error': 'Failed to authenticate with cloud storage'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            # Télécharger depuis le cloud
            backend = CloudStorageFactory.get_backend(cloud_storage)
            file_content = backend.download_file(document_file.cloud_file_id)
            
            # Sauvegarder localement
            from django.core.files.base import ContentFile
            document_file.file.save(document_file.file_name, ContentFile(file_content), save=False)
            
            # Supprimer du cloud si demandé
            if delete_source:
                backend.delete_file(document_file.cloud_file_id)
            
            # Mettre à jour le DocumentFile
            document_file.storage_type = 'local'
            document_file.cloud_storage = None
            document_file.cloud_file_id = None
            document_file.cloud_file_path = None
            document_file.cloud_url = None
            document_file.cloud_metadata = {}
            document_file.sync_status = None
            document_file.sync_error = None
            document_file.last_synced = None
            document_file.save()
            
            # Logger l'activité
            CloudStorageActivity.objects.create(
                user_storage=cloud_storage,
                action='download',
                document_file=document_file,
                details=f'File moved from {cloud_storage.display_name} to local'
            )
            
            return Response({
                'message': 'File moved to local successfully',
                'file': {
                    'id': document_file.id,
                    'storage_type': document_file.storage_type,
                }
            })
            
        except Exception as e:
            logger.error(f"Failed to move file {file_id} to local: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
