"""
Factory pour instancier les backends de stockage cloud selon le provider.
"""

from cors.models import UserCloudStorage
from cors.storage.backends.base import BaseCloudStorageBackend
import logging

logger = logging.getLogger(__name__)


class CloudStorageFactory:
    """
    Factory pour créer des instances de backends de stockage cloud.
    """
    
    _backends = {}
    
    @classmethod
    def get_backend(cls, user_storage: UserCloudStorage) -> BaseCloudStorageBackend:
        """
        Récupère une instance de backend pour le provider spécifié.
        
        Args:
            user_storage: Instance de UserCloudStorage
            
        Returns:
            Instance du backend approprié
            
        Raises:
            ValueError: Si le provider n'est pas supporté
        """
        provider_code = user_storage.provider.code
        
        backend_class = cls._backends.get(provider_code)
        if not backend_class:
            raise ValueError(
                f"Provider '{provider_code}' not supported. "
                f"Available providers: {list(cls._backends.keys())}"
            )
        
        logger.info(f"Initializing {provider_code} backend for user {user_storage.user.email}")
        return backend_class(user_storage)
    
    @classmethod
    def register_backend(cls, provider_code: str, backend_class):
        """
        Enregistre un nouveau backend.
        Permet d'ajouter dynamiquement des providers.
        
        Args:
            provider_code: Code du provider (ex: 'google_drive')
            backend_class: Classe du backend (doit hériter de BaseCloudStorageBackend)
        """
        if not issubclass(backend_class, BaseCloudStorageBackend):
            raise ValueError(
                f"{backend_class} must inherit from BaseCloudStorageBackend"
            )
        
        cls._backends[provider_code] = backend_class
        logger.info(f"Registered backend for provider: {provider_code}")
    
    @classmethod
    def get_supported_providers(cls) -> list:
        """
        Retourne la liste des providers supportés.
        
        Returns:
            Liste des codes de providers
        """
        return list(cls._backends.keys())


# Note: Les backends concrets (Google Drive, OneDrive, etc.) seront importés
# et enregistrés automatiquement via leurs fichiers __init__.py ou signals.py
