"""
Interface abstraite pour les backends de stockage cloud.
Tous les backends (Google Drive, OneDrive, Dropbox, etc.) doivent implémenter cette interface.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, BinaryIO


class BaseCloudStorageBackend(ABC):
    """
    Interface de base pour tous les backends de stockage cloud.
    """
    
    def __init__(self, user_storage):
        """
        Initialise le backend avec une connexion UserCloudStorage.
        
        Args:
            user_storage: Instance de UserCloudStorage
        """
        self.user_storage = user_storage
    
    @abstractmethod
    def authenticate(self, code: str) -> Dict[str, any]:
        """
        Authentification OAuth et récupération des tokens.
        
        Args:
            code: Code d'autorisation OAuth
            
        Returns:
            Dict contenant access_token, refresh_token, expires_in, etc.
        """
        pass
    
    @abstractmethod
    def refresh_token(self, refresh_token: str) -> Dict[str, any]:
        """
        Rafraîchir le token d'accès.
        
        Args:
            refresh_token: Refresh token actuel
            
        Returns:
            Dict contenant les nouveaux tokens
        """
        pass
    
    @abstractmethod
    def upload_file(self, file: BinaryIO, path: str, metadata: Dict[str, any]) -> Dict[str, any]:
        """
        Upload un fichier vers le cloud storage.
        
        Args:
            file: Fichier à uploader (file-like object)
            path: Chemin de destination (relatif au base_folder)
            metadata: Métadonnées du fichier (name, mime_type, etc.)
            
        Returns:
            Dict contenant file_id, name, size, url, metadata
        """
        pass
    
    @abstractmethod
    def download_file(self, file_id: str) -> bytes:
        """
        Télécharge un fichier depuis le cloud storage.
        
        Args:
            file_id: ID du fichier chez le provider
            
        Returns:
            Contenu du fichier en bytes
        """
        pass
    
    @abstractmethod
    def delete_file(self, file_id: str) -> bool:
        """
        Supprime un fichier du cloud storage.
        
        Args:
            file_id: ID du fichier à supprimer
            
        Returns:
            True si suppression réussie, False sinon
        """
        pass
    
    @abstractmethod
    def get_file_info(self, file_id: str) -> Dict[str, any]:
        """
        Récupère les informations d'un fichier.
        
        Args:
            file_id: ID du fichier
            
        Returns:
            Dict contenant name, size, modified_time, etc.
        """
        pass
    
    @abstractmethod
    def list_files(self, folder_id: Optional[str] = None, path: Optional[str] = None) -> List[Dict[str, any]]:
        """
        Liste les fichiers d'un dossier.
        
        Args:
            folder_id: ID du dossier (ou None pour racine)
            path: Chemin du dossier (alternative à folder_id)
            
        Returns:
            Liste de dicts avec infos des fichiers
        """
        pass
    
    @abstractmethod
    def create_folder(self, name: str, parent_id: Optional[str] = None, parent_path: Optional[str] = None) -> Dict[str, any]:
        """
        Crée un dossier.
        
        Args:
            name: Nom du dossier
            parent_id: ID du dossier parent (ou None pour racine)
            parent_path: Chemin du parent (alternative à parent_id)
            
        Returns:
            Dict contenant folder_id, name, path
        """
        pass
    
    @abstractmethod
    def get_quota_info(self) -> Dict[str, any]:
        """
        Récupère les informations de quota/espace disponible.
        
        Returns:
            Dict contenant total_space, used_space, available_space (en bytes)
        """
        pass
    
    @abstractmethod
    def get_share_link(self, file_id: str, expires: Optional[int] = None) -> str:
        """
        Génère un lien de partage/téléchargement pour un fichier.
        
        Args:
            file_id: ID du fichier
            expires: Durée de validité en secondes (ou None pour permanent)
            
        Returns:
            URL de partage
        """
        pass
