"""
Gestionnaire de tokens OAuth pour les connexions cloud storage.
Gère le rafraîchissement automatique des tokens expirés.
"""

from django.utils import timezone
from datetime import timedelta
from cors.models import UserCloudStorage
from cors.storage.factory import CloudStorageFactory
import logging

logger = logging.getLogger(__name__)


class TokenManager:
    """
    Gestionnaire pour le rafraîchissement automatique des tokens OAuth.
    """
    
    @staticmethod
    def ensure_valid_token(user_storage: UserCloudStorage) -> bool:
        """
        Vérifie et rafraîchit le token si nécessaire.
        
        Args:
            user_storage: Instance de UserCloudStorage
            
        Returns:
            True si le token est valide (ou a été rafraîchi), False en cas d'erreur
        """
        # Si pas de date d'expiration, on considère le token valide
        if not user_storage.token_expires_at:
            return True
        
        # Si le token expire dans moins de 5 minutes, on le rafraîchit
        now = timezone.now()
        expires_soon = now >= (user_storage.token_expires_at - timedelta(minutes=5))
        
        if not expires_soon:
            # Token encore valide
            return True
        
        # Rafraîchir le token
        logger.info(f"Refreshing token for {user_storage}")
        
        try:
            backend = CloudStorageFactory.get_backend(user_storage)
            new_tokens = backend.refresh_token(user_storage.refresh_token)
            
            # Mettre à jour les tokens
            user_storage.access_token = new_tokens['access_token']
            
            if 'refresh_token' in new_tokens:
                user_storage.refresh_token = new_tokens['refresh_token']
            
            expires_in = new_tokens.get('expires_in', 3600)
            user_storage.token_expires_at = now + timedelta(seconds=expires_in)
            user_storage.save()
            
            logger.info(f"Token refreshed successfully for {user_storage}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to refresh token for {user_storage}: {e}")
            # Marquer la connexion comme inactive
            user_storage.is_active = False
            user_storage.save()
            return False
    
    @staticmethod
    def revoke_token(user_storage: UserCloudStorage):
        """
        Révoque un token (déconnexion).
        
        Args:
            user_storage: Instance de UserCloudStorage
        """
        try:
            # Certains providers ont un endpoint de révocation
            # Pour l'instant, on se contente de marquer comme inactif
            user_storage.is_active = False
            user_storage.save()
            
            logger.info(f"Token revoked for {user_storage}")
            
        except Exception as e:
            logger.error(f"Failed to revoke token for {user_storage}: {e}")
