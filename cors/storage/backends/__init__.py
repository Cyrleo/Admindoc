"""
Auto-registration des backends cloud storage.
Importe et enregistre automatiquement tous les backends disponibles.
"""

from cors.storage.factory import CloudStorageFactory
from cors.models import CloudStorageProvider
import logging

logger = logging.getLogger(__name__)


def register_backends():
    """Enregistre tous les backends cloud storage disponibles."""
    
    # Google Drive
    try:
        from cors.storage.backends.google_drive import GoogleDriveBackend
        CloudStorageFactory.register_backend(
            CloudStorageProvider.PROVIDER_GOOGLE_DRIVE,
            GoogleDriveBackend
        )
        logger.info("Google Drive backend registered")
    except ImportError as e:
        logger.warning(f"Google Drive backend not available: {e}")
    
    # OneDrive
    try:
        from cors.storage.backends.onedrive import OneDriveBackend
        CloudStorageFactory.register_backend(
            CloudStorageProvider.PROVIDER_ONEDRIVE,
            OneDriveBackend
        )
        logger.info("OneDrive backend registered")
    except ImportError as e:
        logger.warning(f"OneDrive backend not available: {e}")
    
    # Dropbox
    try:
        from cors.storage.backends.dropbox import DropboxBackend
        CloudStorageFactory.register_backend(
            CloudStorageProvider.PROVIDER_DROPBOX,
            DropboxBackend
        )
        logger.info("Dropbox backend registered")
    except ImportError as e:
        logger.warning(f"Dropbox backend not available: {e}")


# Auto-registration au chargement du module
register_backends()
