"""
Backend de stockage cloud pour Google Drive.
Utilise l'API Google Drive v3 avec OAuth 2.0.
"""

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from google.auth.transport.requests import Request
from django.conf import settings
from cors.storage.backends.base import BaseCloudStorageBackend
from typing import Dict, List, Optional, BinaryIO
import io
import logging

logger = logging.getLogger(__name__)


class GoogleDriveBackend(BaseCloudStorageBackend):
    """
    Backend pour Google Drive API v3.
    """
    
    SCOPES = settings.GOOGLE_DRIVE_SCOPES
    
    def __init__(self, user_storage):
        super().__init__(user_storage)
        self._service = None
    
    @property
    def service(self):
        """Lazy initialization du service Google Drive."""
        if not self._service:
            creds = self._get_credentials()
            self._service = build('drive', 'v3', credentials=creds)
        return self._service
    
    def _get_credentials(self) -> Credentials:
        """
        Récupère les credentials Google OAuth depuis user_storage.
        
        Returns:
            Credentials object pour Google API
        """
        creds = Credentials(
            token=self.user_storage.access_token,
            refresh_token=self.user_storage.refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=settings.GOOGLE_DRIVE_CLIENT_ID,
            client_secret=settings.GOOGLE_DRIVE_CLIENT_SECRET,
            scopes=self.SCOPES
        )
        return creds
    
    @classmethod
    def get_authorization_url(cls, state: str = None) -> str:
        """
        Génère l'URL d'autorisation OAuth pour Google Drive.
        
        Args:
            state: État CSRF pour sécuriser la requête
            
        Returns:
            URL d'autorisation Google OAuth
        """
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": settings.GOOGLE_DRIVE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_DRIVE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [settings.GOOGLE_DRIVE_REDIRECT_URI],
                }
            },
            scopes=cls.SCOPES,
        )
        flow.redirect_uri = settings.GOOGLE_DRIVE_REDIRECT_URI
        
        authorization_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            state=state,
            prompt='consent'
        )
        
        return authorization_url
    
    def authenticate(self, code: str) -> Dict[str, any]:
        """
        Authentification OAuth et récupération des tokens.
        
        Args:
            code: Code d'autorisation OAuth reçu du callback
            
        Returns:
            Dict contenant access_token, refresh_token, expires_in, account_info
        """
        try:
            flow = Flow.from_client_config(
                {
                    "web": {
                        "client_id": settings.GOOGLE_DRIVE_CLIENT_ID,
                        "client_secret": settings.GOOGLE_DRIVE_CLIENT_SECRET,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": [settings.GOOGLE_DRIVE_REDIRECT_URI],
                    }
                },
                scopes=self.SCOPES,
            )
            flow.redirect_uri = settings.GOOGLE_DRIVE_REDIRECT_URI
            
            # Échanger le code contre les tokens
            flow.fetch_token(code=code)
            creds = flow.credentials
            
            # Récupérer les infos du compte
            service = build('drive', 'v3', credentials=creds)
            about = service.about().get(fields='user, storageQuota').execute()
            
            user_info = about.get('user', {})
            
            return {
                'access_token': creds.token,
                'refresh_token': creds.refresh_token,
                'expires_in': 3600,  # Google tokens expirent généralement après 1h
                'account_info': {
                    'id': user_info.get('permissionId', ''),
                    'email': user_info.get('emailAddress', ''),
                    'name': user_info.get('displayName', ''),
                    'picture': user_info.get('photoLink', ''),
                }
            }
            
        except Exception as e:
            logger.error(f"Google Drive authentication failed: {e}")
            raise
    
    def refresh_token(self, refresh_token: str) -> Dict[str, any]:
        """
        Rafraîchir le token d'accès.
        
        Args:
            refresh_token: Refresh token actuel
            
        Returns:
            Dict contenant les nouveaux tokens
        """
        try:
            creds = Credentials(
                token=None,
                refresh_token=refresh_token,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=settings.GOOGLE_DRIVE_CLIENT_ID,
                client_secret=settings.GOOGLE_DRIVE_CLIENT_SECRET,
                scopes=self.SCOPES
            )
            
            # Forcer le rafraîchissement
            creds.refresh(Request())
            
            return {
                'access_token': creds.token,
                'refresh_token': creds.refresh_token or refresh_token,
                'expires_in': 3600,
            }
            
        except Exception as e:
            logger.error(f"Google Drive token refresh failed: {e}")
            raise
    
    def upload_file(self, file: BinaryIO, path: str, metadata: Dict[str, any]) -> Dict[str, any]:
        """
        Upload un fichier vers Google Drive.
        
        Args:
            file: Fichier à uploader (file-like object)
            path: Chemin de destination (utilisé pour créer/trouver le dossier)
            metadata: Métadonnées du fichier (name, mime_type)
            
        Returns:
            Dict contenant file_id, name, size, url, metadata
        """
        try:
            # Trouver ou créer le dossier de destination
            folder_id = self._ensure_folder_path(path)
            
            file_metadata = {
                'name': metadata.get('name', 'Untitled'),
                'parents': [folder_id] if folder_id else [],
            }
            
            media = MediaIoBaseUpload(
                file,
                mimetype=metadata.get('mime_type', 'application/octet-stream'),
                resumable=True
            )
            
            uploaded_file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, size, mimeType, webViewLink, webContentLink, createdTime, modifiedTime'
            ).execute()
            
            logger.info(f"File uploaded to Google Drive: {uploaded_file.get('name')} (ID: {uploaded_file.get('id')})")
            
            return {
                'file_id': uploaded_file.get('id'),
                'name': uploaded_file.get('name'),
                'size': int(uploaded_file.get('size', 0)),
                'url': uploaded_file.get('webViewLink', ''),
                'download_url': uploaded_file.get('webContentLink', ''),
                'metadata': {
                    'mime_type': uploaded_file.get('mimeType'),
                    'created_time': uploaded_file.get('createdTime'),
                    'modified_time': uploaded_file.get('modifiedTime'),
                },
                'path': path,
            }
            
        except Exception as e:
            logger.error(f"Google Drive upload failed: {e}")
            raise
    
    def download_file(self, file_id: str) -> bytes:
        """
        Télécharge un fichier depuis Google Drive.
        
        Args:
            file_id: ID du fichier Google Drive
            
        Returns:
            Contenu du fichier en bytes
        """
        try:
            request = self.service.files().get_media(fileId=file_id)
            file_buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(file_buffer, request)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    logger.debug(f"Download progress: {int(status.progress() * 100)}%")
            
            logger.info(f"File downloaded from Google Drive: {file_id}")
            return file_buffer.getvalue()
            
        except Exception as e:
            logger.error(f"Google Drive download failed for file {file_id}: {e}")
            raise
    
    def delete_file(self, file_id: str) -> bool:
        """
        Supprime un fichier de Google Drive.
        
        Args:
            file_id: ID du fichier à supprimer
            
        Returns:
            True si suppression réussie
        """
        try:
            self.service.files().delete(fileId=file_id).execute()
            logger.info(f"File deleted from Google Drive: {file_id}")
            return True
            
        except Exception as e:
            logger.error(f"Google Drive delete failed for file {file_id}: {e}")
            return False
    
    def get_file_info(self, file_id: str) -> Dict[str, any]:
        """
        Récupère les informations d'un fichier.
        
        Args:
            file_id: ID du fichier
            
        Returns:
            Dict contenant name, size, modified_time, etc.
        """
        try:
            file_info = self.service.files().get(
                fileId=file_id,
                fields='id, name, size, mimeType, createdTime, modifiedTime, webViewLink, parents'
            ).execute()
            
            return {
                'id': file_info.get('id'),
                'name': file_info.get('name'),
                'size': int(file_info.get('size', 0)),
                'mime_type': file_info.get('mimeType'),
                'created_time': file_info.get('createdTime'),
                'modified_time': file_info.get('modifiedTime'),
                'url': file_info.get('webViewLink'),
                'parents': file_info.get('parents', []),
            }
            
        except Exception as e:
            logger.error(f"Failed to get file info for {file_id}: {e}")
            raise
    
    def list_files(self, folder_id: Optional[str] = None, path: Optional[str] = None) -> List[Dict[str, any]]:
        """
        Liste les fichiers d'un dossier.
        
        Args:
            folder_id: ID du dossier Google Drive
            path: Chemin du dossier (alternative)
            
        Returns:
            Liste de dicts avec infos des fichiers
        """
        try:
            if path and not folder_id:
                folder_id = self._find_folder_by_path(path)
            
            query = f"'{folder_id}' in parents" if folder_id else "trashed = false"
            
            results = self.service.files().list(
                q=query,
                fields='files(id, name, size, mimeType, createdTime, modifiedTime, webViewLink)',
                pageSize=100,
                orderBy='modifiedTime desc'
            ).execute()
            
            files = results.get('files', [])
            
            return [
                {
                    'id': f.get('id'),
                    'name': f.get('name'),
                    'size': int(f.get('size', 0)) if f.get('size') else 0,
                    'mime_type': f.get('mimeType'),
                    'created_time': f.get('createdTime'),
                    'modified_time': f.get('modifiedTime'),
                    'url': f.get('webViewLink'),
                    'is_folder': f.get('mimeType') == 'application/vnd.google-apps.folder',
                }
                for f in files
            ]
            
        except Exception as e:
            logger.error(f"Failed to list files: {e}")
            raise
    
    def create_folder(self, name: str, parent_id: Optional[str] = None, parent_path: Optional[str] = None) -> Dict[str, any]:
        """
        Crée un dossier dans Google Drive.
        
        Args:
            name: Nom du dossier
            parent_id: ID du dossier parent
            parent_path: Chemin du parent (alternative)
            
        Returns:
            Dict contenant folder_id, name, path
        """
        try:
            if parent_path and not parent_id:
                parent_id = self._find_folder_by_path(parent_path)
            
            folder_metadata = {
                'name': name,
                'mimeType': 'application/vnd.google-apps.folder',
            }
            
            if parent_id:
                folder_metadata['parents'] = [parent_id]
            
            folder = self.service.files().create(
                body=folder_metadata,
                fields='id, name, parents'
            ).execute()
            
            logger.info(f"Folder created in Google Drive: {folder.get('name')} (ID: {folder.get('id')})")
            
            return {
                'folder_id': folder.get('id'),
                'name': folder.get('name'),
                'parent_id': parent_id,
            }
            
        except Exception as e:
            logger.error(f"Failed to create folder {name}: {e}")
            raise
    
    def get_quota_info(self) -> Dict[str, any]:
        """
        Récupère les informations de quota/espace disponible.
        
        Returns:
            Dict contenant total_space, used_space, available_space (en bytes)
        """
        try:
            about = self.service.about().get(fields='storageQuota').execute()
            quota = about.get('storageQuota', {})
            
            total = int(quota.get('limit', 0))
            used = int(quota.get('usage', 0))
            
            return {
                'total_space': total,
                'used_space': used,
                'available_space': total - used if total > 0 else 0,
                'in_trash': int(quota.get('usageInDriveTrash', 0)),
            }
            
        except Exception as e:
            logger.error(f"Failed to get quota info: {e}")
            raise
    
    def get_share_link(self, file_id: str, expires: Optional[int] = None) -> str:
        """
        Génère un lien de partage pour un fichier.
        
        Args:
            file_id: ID du fichier
            expires: Non utilisé pour Google Drive (pas de liens temporaires)
            
        Returns:
            URL de partage
        """
        try:
            # Rendre le fichier accessible via le lien
            permission = {
                'type': 'anyone',
                'role': 'reader',
            }
            
            self.service.permissions().create(
                fileId=file_id,
                body=permission,
                fields='id'
            ).execute()
            
            # Récupérer le lien de partage
            file_info = self.service.files().get(
                fileId=file_id,
                fields='webViewLink, webContentLink'
            ).execute()
            
            return file_info.get('webViewLink', file_info.get('webContentLink', ''))
            
        except Exception as e:
            logger.error(f"Failed to create share link for {file_id}: {e}")
            raise
    
    # --- Méthodes utilitaires ---
    
    def _find_folder_by_path(self, path: str) -> Optional[str]:
        """
        Trouve un dossier par son chemin.
        
        Args:
            path: Chemin du dossier (ex: "AdminDoc/Factures/")
            
        Returns:
            ID du dossier ou None
        """
        parts = [p for p in path.strip('/').split('/') if p]
        
        if not parts:
            return None  # root
        
        parent_id = None
        
        for part in parts:
            query = f"name = '{part}' and mimeType = 'application/vnd.google-apps.folder'"
            if parent_id:
                query += f" and '{parent_id}' in parents"
            
            results = self.service.files().list(
                q=query,
                fields='files(id, name)',
                pageSize=1
            ).execute()
            
            files = results.get('files', [])
            if not files:
                return None
            
            parent_id = files[0]['id']
        
        return parent_id
    
    def _ensure_folder_path(self, path: str) -> Optional[str]:
        """
        Assure qu'un chemin de dossiers existe, en créant les dossiers manquants.
        
        Args:
            path: Chemin du dossier (ex: "AdminDoc/Factures/")
            
        Returns:
            ID du dossier final
        """
        parts = [p for p in path.strip('/').split('/') if p]
        
        if not parts:
            return None  # root
        
        parent_id = None
        
        for part in parts:
            # Chercher si le dossier existe
            query = f"name = '{part}' and mimeType = 'application/vnd.google-apps.folder'"
            if parent_id:
                query += f" and '{parent_id}' in parents"
            
            results = self.service.files().list(
                q=query,
                fields='files(id, name)',
                pageSize=1
            ).execute()
            
            files = results.get('files', [])
            
            if files:
                parent_id = files[0]['id']
            else:
                # Créer le dossier
                folder = self.create_folder(part, parent_id=parent_id)
                parent_id = folder['folder_id']
        
        return parent_id
