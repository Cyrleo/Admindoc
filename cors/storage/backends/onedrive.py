"""
Backend de stockage cloud pour Microsoft OneDrive.
Utilise Microsoft Graph API avec MSAL (Microsoft Authentication Library).
"""

from msal import ConfidentialClientApplication
from django.conf import settings
from cors.storage.backends.base import BaseCloudStorageBackend
from typing import Dict, List, Optional, BinaryIO
import requests
import logging
import io

logger = logging.getLogger(__name__)


class OneDriveBackend(BaseCloudStorageBackend):
    """
    Backend pour Microsoft OneDrive via Graph API.
    """
    
    GRAPH_API_ENDPOINT = 'https://graph.microsoft.com/v1.0'
    AUTHORITY = 'https://login.microsoftonline.com/common'
    SCOPES = settings.ONEDRIVE_SCOPES
    
    def __init__(self, user_storage):
        super().__init__(user_storage)
        self._access_token = None
    
    def _get_access_token(self) -> str:
        """Récupère le token d'accès (avec refresh si nécessaire)."""
        if not self._access_token:
            self._access_token = self.user_storage.access_token
        return self._access_token
    
    def _get_headers(self) -> Dict[str, str]:
        """Headers HTTP pour les requêtes Graph API."""
        return {
            'Authorization': f'Bearer {self._get_access_token()}',
            'Content-Type': 'application/json',
        }
    
    @classmethod
    def get_authorization_url(cls, state: str = None) -> str:
        """
        Génère l'URL d'autorisation OAuth pour OneDrive.
        
        Args:
            state: État CSRF pour sécuriser la requête
            
        Returns:
            URL d'autorisation Microsoft OAuth
        """
        app = ConfidentialClientApplication(
            settings.ONEDRIVE_CLIENT_ID,
            authority=cls.AUTHORITY,
            client_credential=settings.ONEDRIVE_CLIENT_SECRET,
        )
        
        auth_url = app.get_authorization_request_url(
            scopes=cls.SCOPES,
            state=state,
            redirect_uri=settings.ONEDRIVE_REDIRECT_URI,
        )
        
        return auth_url
    
    def authenticate(self, code: str) -> Dict[str, any]:
        """
        Authentification OAuth et récupération des tokens.
        
        Args:
            code: Code d'autorisation OAuth reçu du callback
            
        Returns:
            Dict contenant access_token, refresh_token, expires_in, account_info
        """
        try:
            app = ConfidentialClientApplication(
                settings.ONEDRIVE_CLIENT_ID,
                authority=self.AUTHORITY,
                client_credential=settings.ONEDRIVE_CLIENT_SECRET,
            )
            
            # Échanger le code contre les tokens
            result = app.acquire_token_by_authorization_code(
                code,
                scopes=self.SCOPES,
                redirect_uri=settings.ONEDRIVE_REDIRECT_URI,
            )
            
            if 'error' in result:
                raise Exception(f"OneDrive OAuth error: {result.get('error_description', result['error'])}")
            
            # Récupérer les infos du compte
            headers = {'Authorization': f'Bearer {result["access_token"]}'}
            user_response = requests.get(
                f'{self.GRAPH_API_ENDPOINT}/me',
                headers=headers
            )
            user_response.raise_for_status()
            user_info = user_response.json()
            
            return {
                'access_token': result['access_token'],
                'refresh_token': result.get('refresh_token', ''),
                'expires_in': result.get('expires_in', 3600),
                'account_info': {
                    'id': user_info.get('id', ''),
                    'email': user_info.get('userPrincipalName', ''),
                    'name': user_info.get('displayName', ''),
                }
            }
            
        except Exception as e:
            logger.error(f"OneDrive authentication failed: {e}")
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
            app = ConfidentialClientApplication(
                settings.ONEDRIVE_CLIENT_ID,
                authority=self.AUTHORITY,
                client_credential=settings.ONEDRIVE_CLIENT_SECRET,
            )
            
            result = app.acquire_token_by_refresh_token(
                refresh_token,
                scopes=self.SCOPES
            )
            
            if 'error' in result:
                raise Exception(f"Token refresh error: {result.get('error_description', result['error'])}")
            
            self._access_token = result['access_token']
            
            return {
                'access_token': result['access_token'],
                'refresh_token': result.get('refresh_token', refresh_token),
                'expires_in': result.get('expires_in', 3600),
            }
            
        except Exception as e:
            logger.error(f"OneDrive token refresh failed: {e}")
            raise
    
    def upload_file(self, file: BinaryIO, path: str, metadata: Dict[str, any]) -> Dict[str, any]:
        """
        Upload un fichier vers OneDrive.
        
        Args:
            file: Fichier à uploader (file-like object)
            path: Chemin de destination
            metadata: Métadonnées du fichier (name, mime_type)
            
        Returns:
            Dict contenant file_id, name, size, url, metadata
        """
        try:
            # Lire le contenu du fichier
            file_content = file.read()
            file_size = len(file_content)
            file_name = metadata.get('name', 'Untitled')
            
            # Assurer que le dossier existe
            folder_path = path.rstrip('/')
            if folder_path:
                self._ensure_folder_path(folder_path)
            
            # Construire le chemin complet du fichier
            full_path = f"{folder_path}/{file_name}" if folder_path else file_name
            
            # Upload simple pour fichiers < 4MB, chunked pour fichiers plus gros
            if file_size < 4 * 1024 * 1024:  # 4 MB
                # Simple upload
                upload_url = f"{self.GRAPH_API_ENDPOINT}/me/drive/root:/{full_path}:/content"
                
                headers = {
                    'Authorization': f'Bearer {self._get_access_token()}',
                    'Content-Type': metadata.get('mime_type', 'application/octet-stream'),
                }
                
                response = requests.put(
                    upload_url,
                    headers=headers,
                    data=file_content
                )
                response.raise_for_status()
                result = response.json()
            else:
                # Chunked upload pour gros fichiers
                result = self._upload_large_file(full_path, file_content, metadata)
            
            logger.info(f"File uploaded to OneDrive: {result.get('name')} (ID: {result.get('id')})")
            
            return {
                'file_id': result.get('id'),
                'name': result.get('name'),
                'size': result.get('size', file_size),
                'url': result.get('webUrl', ''),
                'download_url': result.get('@microsoft.graph.downloadUrl', ''),
                'metadata': {
                    'mime_type': result.get('file', {}).get('mimeType'),
                    'created_time': result.get('createdDateTime'),
                    'modified_time': result.get('lastModifiedDateTime'),
                },
                'path': path,
            }
            
        except Exception as e:
            logger.error(f"OneDrive upload failed: {e}")
            raise
    
    def _upload_large_file(self, file_path: str, file_content: bytes, metadata: Dict) -> Dict:
        """Upload un gros fichier par chunks."""
        # Créer une session d'upload
        upload_session_url = f"{self.GRAPH_API_ENDPOINT}/me/drive/root:/{file_path}:/createUploadSession"
        
        response = requests.post(
            upload_session_url,
            headers=self._get_headers(),
            json={'item': {'@microsoft.graph.conflictBehavior': 'replace'}}
        )
        response.raise_for_status()
        upload_url = response.json()['uploadUrl']
        
        # Uploader par chunks de 10MB
        chunk_size = 10 * 1024 * 1024  # 10 MB
        file_size = len(file_content)
        
        for start in range(0, file_size, chunk_size):
            end = min(start + chunk_size, file_size)
            chunk = file_content[start:end]
            
            headers = {
                'Content-Length': str(len(chunk)),
                'Content-Range': f'bytes {start}-{end-1}/{file_size}'
            }
            
            response = requests.put(upload_url, headers=headers, data=chunk)
            response.raise_for_status()
            
            logger.debug(f"Uploaded chunk {start}-{end} of {file_size}")
        
        return response.json()
    
    def download_file(self, file_id: str) -> bytes:
        """
        Télécharge un fichier depuis OneDrive.
        
        Args:
            file_id: ID du fichier OneDrive
            
        Returns:
            Contenu du fichier en bytes
        """
        try:
            # Obtenir l'URL de téléchargement
            url = f"{self.GRAPH_API_ENDPOINT}/me/drive/items/{file_id}/content"
            
            response = requests.get(
                url,
                headers=self._get_headers(),
                allow_redirects=True
            )
            response.raise_for_status()
            
            logger.info(f"File downloaded from OneDrive: {file_id}")
            return response.content
            
        except Exception as e:
            logger.error(f"OneDrive download failed for file {file_id}: {e}")
            raise
    
    def delete_file(self, file_id: str) -> bool:
        """
        Supprime un fichier de OneDrive.
        
        Args:
            file_id: ID du fichier à supprimer
            
        Returns:
            True si suppression réussie
        """
        try:
            url = f"{self.GRAPH_API_ENDPOINT}/me/drive/items/{file_id}"
            
            response = requests.delete(url, headers=self._get_headers())
            response.raise_for_status()
            
            logger.info(f"File deleted from OneDrive: {file_id}")
            return True
            
        except Exception as e:
            logger.error(f"OneDrive delete failed for file {file_id}: {e}")
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
            url = f"{self.GRAPH_API_ENDPOINT}/me/drive/items/{file_id}"
            
            response = requests.get(url, headers=self._get_headers())
            response.raise_for_status()
            file_info = response.json()
            
            return {
                'id': file_info.get('id'),
                'name': file_info.get('name'),
                'size': file_info.get('size', 0),
                'mime_type': file_info.get('file', {}).get('mimeType'),
                'created_time': file_info.get('createdDateTime'),
                'modified_time': file_info.get('lastModifiedDateTime'),
                'url': file_info.get('webUrl'),
                'is_folder': 'folder' in file_info,
            }
            
        except Exception as e:
            logger.error(f"Failed to get file info for {file_id}: {e}")
            raise
    
    def list_files(self, folder_id: Optional[str] = None, path: Optional[str] = None) -> List[Dict[str, any]]:
        """
        Liste les fichiers d'un dossier.
        
        Args:
            folder_id: ID du dossier OneDrive
            path: Chemin du dossier (alternative)
            
        Returns:
            Liste de dicts avec infos des fichiers
        """
        try:
            if path:
                url = f"{self.GRAPH_API_ENDPOINT}/me/drive/root:/{path}:/children"
            elif folder_id:
                url = f"{self.GRAPH_API_ENDPOINT}/me/drive/items/{folder_id}/children"
            else:
                url = f"{self.GRAPH_API_ENDPOINT}/me/drive/root/children"
            
            response = requests.get(url, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()
            
            files = []
            for item in data.get('value', []):
                files.append({
                    'id': item.get('id'),
                    'name': item.get('name'),
                    'size': item.get('size', 0),
                    'mime_type': item.get('file', {}).get('mimeType') if 'file' in item else None,
                    'created_time': item.get('createdDateTime'),
                    'modified_time': item.get('lastModifiedDateTime'),
                    'url': item.get('webUrl'),
                    'is_folder': 'folder' in item,
                })
            
            return files
            
        except Exception as e:
            logger.error(f"Failed to list files: {e}")
            raise
    
    def create_folder(self, name: str, parent_id: Optional[str] = None, parent_path: Optional[str] = None) -> Dict[str, any]:
        """
        Crée un dossier dans OneDrive.
        
        Args:
            name: Nom du dossier
            parent_id: ID du dossier parent
            parent_path: Chemin du parent (alternative)
            
        Returns:
            Dict contenant folder_id, name, path
        """
        try:
            if parent_path:
                url = f"{self.GRAPH_API_ENDPOINT}/me/drive/root:/{parent_path}:/children"
            elif parent_id:
                url = f"{self.GRAPH_API_ENDPOINT}/me/drive/items/{parent_id}/children"
            else:
                url = f"{self.GRAPH_API_ENDPOINT}/me/drive/root/children"
            
            folder_data = {
                'name': name,
                'folder': {},
                '@microsoft.graph.conflictBehavior': 'rename'
            }
            
            response = requests.post(
                url,
                headers=self._get_headers(),
                json=folder_data
            )
            response.raise_for_status()
            folder = response.json()
            
            logger.info(f"Folder created in OneDrive: {folder.get('name')} (ID: {folder.get('id')})")
            
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
            url = f"{self.GRAPH_API_ENDPOINT}/me/drive"
            
            response = requests.get(url, headers=self._get_headers())
            response.raise_for_status()
            drive_info = response.json()
            
            quota = drive_info.get('quota', {})
            total = quota.get('total', 0)
            used = quota.get('used', 0)
            
            return {
                'total_space': total,
                'used_space': used,
                'available_space': total - used if total > 0 else 0,
                'deleted': quota.get('deleted', 0),
                'remaining': quota.get('remaining', 0),
            }
            
        except Exception as e:
            logger.error(f"Failed to get quota info: {e}")
            raise
    
    def get_share_link(self, file_id: str, expires: Optional[int] = None) -> str:
        """
        Génère un lien de partage pour un fichier.
        
        Args:
            file_id: ID du fichier
            expires: Durée de validité en secondes (non supporté par OneDrive)
            
        Returns:
            URL de partage
        """
        try:
            url = f"{self.GRAPH_API_ENDPOINT}/me/drive/items/{file_id}/createLink"
            
            link_data = {
                'type': 'view',  # view ou edit
                'scope': 'anonymous'  # anonymous ou organization
            }
            
            response = requests.post(
                url,
                headers=self._get_headers(),
                json=link_data
            )
            response.raise_for_status()
            link_info = response.json()
            
            return link_info.get('link', {}).get('webUrl', '')
            
        except Exception as e:
            logger.error(f"Failed to create share link for {file_id}: {e}")
            raise
    
    def _ensure_folder_path(self, path: str) -> Optional[str]:
        """
        Assure qu'un chemin de dossiers existe, en créant les dossiers manquants.
        
        Args:
            path: Chemin du dossier (ex: "AdminDoc/Factures")
            
        Returns:
            ID du dossier final
        """
        parts = [p for p in path.strip('/').split('/') if p]
        
        if not parts:
            return None
        
        current_path = ""
        
        for part in parts:
            current_path = f"{current_path}/{part}" if current_path else part
            
            # Vérifier si le dossier existe
            try:
                url = f"{self.GRAPH_API_ENDPOINT}/me/drive/root:/{current_path}"
                response = requests.get(url, headers=self._get_headers())
                
                if response.status_code == 404:
                    # Créer le dossier
                    parent_path = "/".join(current_path.split('/')[:-1])
                    self.create_folder(part, parent_path=parent_path if parent_path else None)
            except:
                # En cas d'erreur, essayer de créer
                parent_path = "/".join(current_path.split('/')[:-1])
                self.create_folder(part, parent_path=parent_path if parent_path else None)
        
        # Retourner l'ID du dossier final
        try:
            url = f"{self.GRAPH_API_ENDPOINT}/me/drive/root:/{current_path}"
            response = requests.get(url, headers=self._get_headers())
            response.raise_for_status()
            return response.json().get('id')
        except:
            return None
