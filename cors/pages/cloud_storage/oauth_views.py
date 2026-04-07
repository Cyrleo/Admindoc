"""
Vues pour gérer les callbacks OAuth des providers cloud storage.
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiResponse
from drf_spectacular.openapi import OpenApiTypes
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from cors.models import CloudStorageProvider, UserCloudStorage, CloudStorageActivity
from cors.pages.cloud_storage.serializers import OAuthCallbackResponseSerializer, OAuthInitiateResponseSerializer
from cors.storage.backends.google_drive import GoogleDriveBackend
from cors.storage.backends.onedrive import OneDriveBackend
from cors.storage.backends.dropbox import DropboxBackend
import secrets
import logging

logger = logging.getLogger(__name__)

# Stockage temporaire des états OAuth (en production, utiliser Redis/cache)
# Format: {state: {'user_id': int, 'provider_code': str, 'display_name': str, 'timestamp': datetime}}
_oauth_states = {}


def _cleanup_old_states():
    """Nettoie les états OAuth expirés (>15 minutes)."""
    now = timezone.now()
    expired = [
        state for state, data in _oauth_states.items()
        if (now - data['timestamp']).total_seconds() > 900  # 15 minutes
    ]
    for state in expired:
        del _oauth_states[state]


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@extend_schema(responses=OAuthInitiateResponseSerializer)
def initiate_oauth(request):
    """
    Initie le flow OAuth pour un provider cloud.
    
    POST /api/cloud-storage/oauth/initiate/
    Body: {
        "provider_id": 1,
        "display_name": "Mon Google Drive"  # optionnel
    }
    
    Returns:
        {
            "oauth_url": "https://accounts.google.com/o/oauth2/auth?...",
            "state": "abc123..."
        }
    """
    provider_id = request.data.get('provider_id')
    display_name = request.data.get('display_name', '')
    
    if not provider_id:
        return Response(
            {'error': 'provider_id is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        provider = CloudStorageProvider.objects.get(id=provider_id, is_active=True)
    except CloudStorageProvider.DoesNotExist:
        return Response(
            {'error': f'Provider {provider_id} not found or inactive'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Générer un state CSRF
    state = secrets.token_urlsafe(32)
    
    # Stocker le state avec les infos de l'utilisateur
    _cleanup_old_states()
    _oauth_states[state] = {
        'user_id': request.user.id,
        'provider_code': provider.code,
        'display_name': display_name or f'{provider.name} ({request.user.email})',
        'timestamp': timezone.now(),
    }
    
    # Générer l'URL OAuth selon le provider
    if provider.code == CloudStorageProvider.PROVIDER_GOOGLE_DRIVE:
        oauth_url = GoogleDriveBackend.get_authorization_url(state=state)
    elif provider.code == CloudStorageProvider.PROVIDER_ONEDRIVE:
        oauth_url = OneDriveBackend.get_authorization_url(state=state)
    elif provider.code == CloudStorageProvider.PROVIDER_DROPBOX:
        oauth_url = DropboxBackend.get_authorization_url(state=state)
    else:
        return Response(
            {'error': f'Provider {provider.code} OAuth not supported'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    return Response({
        'oauth_url': oauth_url,
        'state': state,
        'provider': {
            'id': provider.id,
            'code': provider.code,
            'name': provider.name,
        }
    })


@api_view(['GET'])
@extend_schema(responses=OAuthCallbackResponseSerializer)
def oauth_callback_google(request):
    """
    Callback OAuth pour Google Drive.
    
    GET /api/cloud-storage/oauth/callback/google/?code=...&state=...
    
    Après authentification réussie, redirige vers le frontend avec un paramètre de succès.
    """
    code = request.GET.get('code')
    state = request.GET.get('state')
    error = request.GET.get('error')
    
    # Gérer les erreurs OAuth
    if error:
        logger.error(f"Google OAuth error: {error}")
        # TODO: Rediriger vers le frontend avec un message d'erreur
        return Response(
            {'error': f'OAuth authorization failed: {error}'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if not code or not state:
        return Response(
            {'error': 'Missing code or state parameter'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Vérifier le state CSRF
    _cleanup_old_states()
    oauth_data = _oauth_states.get(state)
    
    if not oauth_data:
        return Response(
            {'error': 'Invalid or expired state. Please try again.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Récupérer l'utilisateur et le provider
        from accounts.models import User
        user = User.objects.get(id=oauth_data['user_id'])
        provider = CloudStorageProvider.objects.get(
            code=CloudStorageProvider.PROVIDER_GOOGLE_DRIVE,
            is_active=True
        )
        
        # Échanger le code contre les tokens
        backend = GoogleDriveBackend(user_storage=None)  # Temporaire pour authenticate
        token_data = backend.authenticate(code)
        
        # Créer ou mettre à jour la connexion UserCloudStorage
        account_info = token_data['account_info']
        
        user_storage, created = UserCloudStorage.objects.update_or_create(
            user=user,
            provider=provider,
            cloud_account_id=account_info['id'],
            defaults={
                'access_token': token_data['access_token'],
                'refresh_token': token_data.get('refresh_token', ''),
                'token_expires_at': timezone.now() + timedelta(seconds=token_data.get('expires_in', 3600)),
                'cloud_account_email': account_info.get('email', ''),
                'cloud_account_name': account_info.get('name', ''),
                'display_name': oauth_data['display_name'],
                'is_active': True,
            }
        )
        
        # Si c'est la première connexion cloud de l'utilisateur, la définir comme défaut
        if not UserCloudStorage.objects.filter(user=user, is_default=True).exists():
            user_storage.is_default = True
            user_storage.save()
        
        # Logger l'activité
        CloudStorageActivity.objects.create(
            user_storage=user_storage,
            action='connect' if created else 'sync',
            details=f'Connected to Google Drive account: {account_info.get("email")}'
        )
        
        # Nettoyer le state
        del _oauth_states[state]
        
        logger.info(f"Google Drive connected successfully for user {user.email}")
        
        # TODO: Rediriger vers le frontend avec succès
        # Pour l'instant, retourner un JSON
        return Response({
            'success': True,
            'message': 'Google Drive connected successfully',
            'storage': {
                'id': user_storage.id,
                'provider': provider.name,
                'display_name': user_storage.display_name,
                'account_email': user_storage.cloud_account_email,
                'is_default': user_storage.is_default,
            }
        })
        
    except Exception as e:
        logger.error(f"Google OAuth callback failed: {e}", exc_info=True)
        # Nettoyer le state
        if state in _oauth_states:
            del _oauth_states[state]
        
        return Response(
            {'error': f'Failed to connect Google Drive: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@extend_schema(responses=OAuthCallbackResponseSerializer)
def oauth_callback_onedrive(request):
    """
    Callback OAuth pour Microsoft OneDrive.
    
    GET /api/cloud-storage/oauth/callback/onedrive/?code=...&state=...
    """
    code = request.GET.get('code')
    state = request.GET.get('state')
    error = request.GET.get('error')
    
    # Gérer les erreurs OAuth
    if error:
        logger.error(f"OneDrive OAuth error: {error}")
        return Response(
            {'error': f'OAuth authorization failed: {error}'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if not code or not state:
        return Response(
            {'error': 'Missing code or state parameter'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Vérifier le state CSRF
    _cleanup_old_states()
    oauth_data = _oauth_states.get(state)
    
    if not oauth_data:
        return Response(
            {'error': 'Invalid or expired state. Please try again.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Récupérer l'utilisateur et le provider
        from accounts.models import User
        user = User.objects.get(id=oauth_data['user_id'])
        provider = CloudStorageProvider.objects.get(
            code=CloudStorageProvider.PROVIDER_ONEDRIVE,
            is_active=True
        )
        
        # Échanger le code contre les tokens
        backend = OneDriveBackend(user_storage=None)
        token_data = backend.authenticate(code)
        
        # Créer ou mettre à jour la connexion UserCloudStorage
        account_info = token_data['account_info']
        
        user_storage, created = UserCloudStorage.objects.update_or_create(
            user=user,
            provider=provider,
            cloud_account_id=account_info['id'],
            defaults={
                'access_token': token_data['access_token'],
                'refresh_token': token_data.get('refresh_token', ''),
                'token_expires_at': timezone.now() + timedelta(seconds=token_data.get('expires_in', 3600)),
                'cloud_account_email': account_info.get('email', ''),
                'cloud_account_name': account_info.get('name', ''),
                'display_name': oauth_data['display_name'],
                'is_active': True,
            }
        )
        
        # Si c'est la première connexion cloud de l'utilisateur, la définir comme défaut
        if not UserCloudStorage.objects.filter(user=user, is_default=True).exists():
            user_storage.is_default = True
            user_storage.save()
        
        # Logger l'activité
        CloudStorageActivity.objects.create(
            user_storage=user_storage,
            action='connect' if created else 'sync',
            details=f'Connected to OneDrive account: {account_info.get("email")}'
        )
        
        # Nettoyer le state
        del _oauth_states[state]
        
        logger.info(f"OneDrive connected successfully for user {user.email}")
        
        return Response({
            'success': True,
            'message': 'OneDrive connected successfully',
            'storage': {
                'id': user_storage.id,
                'provider': provider.name,
                'display_name': user_storage.display_name,
                'account_email': user_storage.cloud_account_email,
                'is_default': user_storage.is_default,
            }
        })
        
    except Exception as e:
        logger.error(f"OneDrive OAuth callback failed: {e}", exc_info=True)
        if state in _oauth_states:
            del _oauth_states[state]
        
        return Response(
            {'error': f'Failed to connect OneDrive: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@extend_schema(responses=OAuthCallbackResponseSerializer)
def oauth_callback_dropbox(request):
    """
    Callback OAuth pour Dropbox.
    
    GET /api/cloud-storage/oauth/callback/dropbox/?code=...&state=...
    """
    code = request.GET.get('code')
    state = request.GET.get('state')
    error = request.GET.get('error')
    
    # Gérer les erreurs OAuth
    if error:
        logger.error(f"Dropbox OAuth error: {error}")
        return Response(
            {'error': f'OAuth authorization failed: {error}'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if not code or not state:
        return Response(
            {'error': 'Missing code or state parameter'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Vérifier le state CSRF
    _cleanup_old_states()
    oauth_data = _oauth_states.get(state)
    
    if not oauth_data:
        return Response(
            {'error': 'Invalid or expired state. Please try again.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Récupérer l'utilisateur et le provider
        from accounts.models import User
        user = User.objects.get(id=oauth_data['user_id'])
        provider = CloudStorageProvider.objects.get(
            code=CloudStorageProvider.PROVIDER_DROPBOX,
            is_active=True
        )
        
        # Échanger le code contre les tokens
        backend = DropboxBackend(user_storage=None)
        token_data = backend.authenticate(code)
        
        # Créer ou mettre à jour la connexion UserCloudStorage
        account_info = token_data['account_info']
        
        user_storage, created = UserCloudStorage.objects.update_or_create(
            user=user,
            provider=provider,
            cloud_account_id=account_info['id'],
            defaults={
                'access_token': token_data['access_token'],
                'refresh_token': token_data.get('refresh_token', ''),
                'token_expires_at': timezone.now() + timedelta(days=365) if token_data.get('expires_in', 0) == 0 else timezone.now() + timedelta(seconds=token_data.get('expires_in')),
                'cloud_account_email': account_info.get('email', ''),
                'cloud_account_name': account_info.get('name', ''),
                'display_name': oauth_data['display_name'],
                'is_active': True,
            }
        )
        
        # Si c'est la première connexion cloud de l'utilisateur, la définir comme défaut
        if not UserCloudStorage.objects.filter(user=user, is_default=True).exists():
            user_storage.is_default = True
            user_storage.save()
        
        # Logger l'activité
        CloudStorageActivity.objects.create(
            user_storage=user_storage,
            action='connect' if created else 'sync',
            details=f'Connected to Dropbox account: {account_info.get("email")}'
        )
        
        # Nettoyer le state
        del _oauth_states[state]
        
        logger.info(f"Dropbox connected successfully for user {user.email}")
        
        return Response({
            'success': True,
            'message': 'Dropbox connected successfully',
            'storage': {
                'id': user_storage.id,
                'provider': provider.name,
                'display_name': user_storage.display_name,
                'account_email': user_storage.cloud_account_email,
                'is_default': user_storage.is_default,
            }
        })
        
    except Exception as e:
        logger.error(f"Dropbox OAuth callback failed: {e}", exc_info=True)
        if state in _oauth_states:
            del _oauth_states[state]
        
        return Response(
            {'error': f'Failed to connect Dropbox: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
