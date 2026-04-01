"""
Système de chiffrement pour les tokens OAuth des providers cloud.
Utilise Fernet (cryptography library) pour le chiffrement symétrique.
"""

from cryptography.fernet import Fernet
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class TokenEncryption:
    """
    Chiffrement/déchiffrement des tokens OAuth.
    La clé de chiffrement doit être définie dans settings.CLOUD_STORAGE_ENCRYPTION_KEY
    """
    
    def __init__(self):
        encryption_key = getattr(settings, 'CLOUD_STORAGE_ENCRYPTION_KEY', None)
        
        if not encryption_key:
            # Génération d'une clé par défaut en développement
            # EN PRODUCTION: TOUJOURS DÉFINIR UNE CLÉ DANS LES VARIABLES D'ENVIRONNEMENT!
            logger.warning(
                "CLOUD_STORAGE_ENCRYPTION_KEY not set! Using default key. "
                "THIS IS INSECURE FOR PRODUCTION!"
            )
            encryption_key = Fernet.generate_key().decode()
        
        if isinstance(encryption_key, str):
            encryption_key = encryption_key.encode()
        
        try:
            self.cipher = Fernet(encryption_key)
        except Exception as e:
            logger.error(f"Failed to initialize Fernet cipher: {e}")
            raise ValueError(
                "Invalid CLOUD_STORAGE_ENCRYPTION_KEY. "
                "Generate a new key with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )
    
    def encrypt(self, token: str) -> str:
        """
        Chiffre un token.
        
        Args:
            token: Token en clair
            
        Returns:
            Token chiffré (base64)
        """
        if not token:
            return ''
        
        try:
            encrypted = self.cipher.encrypt(token.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"Token encryption failed: {e}")
            raise
    
    def decrypt(self, encrypted_token: str) -> str:
        """
        Déchiffre un token.
        
        Args:
            encrypted_token: Token chiffré (base64)
            
        Returns:
            Token en clair
        """
        if not encrypted_token:
            return ''
        
        try:
            decrypted = self.cipher.decrypt(encrypted_token.encode())
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Token decryption failed: {e}")
            raise


def generate_encryption_key() -> str:
    """
    Génère une nouvelle clé de chiffrement Fernet.
    À utiliser pour initialiser CLOUD_STORAGE_ENCRYPTION_KEY.
    
    Returns:
        Clé de chiffrement en base64
    """
    key = Fernet.generate_key()
    return key.decode()


if __name__ == '__main__':
    # Génération d'une clé pour le fichier .env
    print("Nouvelle clé de chiffrement:")
    print(f"CLOUD_STORAGE_ENCRYPTION_KEY={generate_encryption_key()}")
