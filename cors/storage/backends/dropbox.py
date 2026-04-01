"""
Backend de stockage cloud pour Dropbox.
Utilise Dropbox SDK avec OAuth 2.0.
"""

from dropbox import Dropbox
from dropbox.files import WriteMode, FileMetadata, FolderMetadata
from dropbox.exceptions import ApiError, AuthError
from dropbox.oauth import DropboxOAuth2FlowNoRedirect
from django.conf import settings
from cors.storage.backends.base import BaseCloudStorageBackend
from typing import Dict, List, Optional, BinaryIO
import logging

logger = logging.getLogger(__name__)


class DropboxBackend(BaseCloudStorageBackend):
    """
    Backend pour Dropbox API v2.
    """
    
    CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB chunks pour uploads
    
    def __init__(self, user_storage):
        super().__init__(user_storage)
        self._dbx = None
    
    @property
    def dbx(self) -> Dropbox:
        """Lazy initialization du client Dropbox."""
        if not self._dbx:
            self._dbx = Dropbox(self.user_storage.access_token)
        return self._dbx
    
    @classmethod
    def get_authorization_url(cls, state: str = None) -> str:
        """
        Génère l'URL d'autorisation OAuth pour Dropbox.
        
        Args:
            state: État CSRF pour sécuriser la requête
            
        Returns:
            URL d'autorisation Dropbox OAuth
        """
        from dropbox.oauth import DropboxOAuth2Flow
        
        oauth_flow = DropboxOAuth2Flow(
            consumer_key=settings.DROPBOX_APP_KEY,
            consumer_secret=settings.DROPBOX_APP_SECRET,
            redirect_uri=settings.DROPBOX_REDIRECT_URI,
            session={},
            csrf_token_session_key='dropbox-auth-csrf-token',
            locale=None
        )
        
        # Pour un flow avec redirect
        auth_url = oauth_flow.start(state)
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
            from dropbox.oauth import DropboxOAuth2Flow
            
            # Échanger le code contre un token
            oauth_flow = DropboxOAuth2Flow(
                consumer_key=settings.DROPBOX_APP_KEY,
                consumer_secret=settings.DROPBOX_APP_SECRET,
                redirect_uri=settings.DROPBOX_REDIRECT_URI,
                session={},
                csrf_token_session_key='dropbox-auth-csrf-token',
            )
            
            # Finaliser le flow OAuth
            oauth_result = oauth_flow.finish({'code': code, 'state': ''})
            access_token = oauth_result.access_token
            
            # Créer un client Dropbox
            dbx = Dropbox(access_token)
            
            # Récupérer les infos du compte
            account_info = dbx.users_get_current_account()
            
            return {
                'access_token': access_token,
                'refresh_token': '',  # Dropbox n'utilise plus de refresh tokens avec les long-lived tokens
                'expires_in': 0,  # Long-lived token, pas d'expiration
                'account_info': {
                    'id': account_info.account_id,
                    'email': account_info.email,
                    'name': account_info.name.display_name,
                }
            }
            
        except AuthError as e:
            logger.error(f"Dropbox authentication failed: {e}")
            raise Exception(f"Dropbox auth error: {str(e)}")
        except Exception as e:
            logger.error(f"Dropbox authentication failed: {e}")
            raise
    
    def refresh_token(self, refresh_token: str) -> Dict[str, any]:
        """
        Rafraîchir le token d'accès.
        Note: Dropbox utilise des long-lived tokens qui n'expirent pas.
        
        Args:
            refresh_token: Refresh token (non utilisé pour Dropbox)
            
        Returns:
            Dict contenant les mêmes tokens
        """
        # Dropbox utilise des long-lived access tokens
        # Pas besoin de rafraîchir
        return {
            'access_token': self.user_storage.access_token,
            'refresh_token': '',
            'expires_in': 0,
        }
    
    def upload_file(self, file: BinaryIO, path: str, metadata: Dict[str, any]) -> Dict[str, any]:
        """
        Upload un fichier vers Dropbox.
        
        Args:
            file: Fichier à uploader (file-like object)
            path: Chemin de destination
            metadata: Métadonnées du fichier (name, mime_type)
            
        Returns:
            Dict contenant file_id, name, size, url, metadata
        """
        try:
            file_name = metadata.get('name', 'Untitled')
            
            # Assurer que le chemin commence par /
            full_path = f"/{path.strip('/')}/{file_name}".replace('//', '/')
            
            # Lire le contenu
            file_content = file.read()
            file_size = len(file_content)
            
            # Upload simple pour petits fichiers, chunked pour gros fichiers
            if file_size <= self.CHUNK_SIZE:
                # Simple upload
                result = self.dbx.files_upload(
                    file_content,
                    full_path,
                    mode=WriteMode('overwrite'),
                    autorename=False,
                    mute=False
                )
            else:
                # Chunked upload pour gros fichiers
                result = self._upload_chunked(file_content, full_path)
            
            logger.info(f"File uploaded to Dropbox: {result.name} (ID: {result.id})")
            
            # Créer un lien de partage
            try:
                share_link = self.get_share_link(result.id)
            except:
                share_link = ''
            
            return {
                'file_id': result.id,
                'name': result.name,
                'size': result.size,
                'url': share_link,
                'metadata': {
                    'path_display': result.path_display,
                    'path_lower': result.path_lower,
                    'client_modified': result.client_modified.isoformat() if hasattr(result, 'client_modified') else None,
                    'server_modified': result.server_modified.isoformat() if hasattr(result, 'server_modified') else None,
                },
                'path': path,
            }
            
        except ApiError as e:
            logger.error(f"Dropbox upload failed: {e}")
            raise Exception(f"Dropbox API error: {str(e)}")
        except Exception as e:
            logger.error(f"Dropbox upload failed: {e}")
            raise
    
    def _upload_chunked(self, file_content: bytes, dropbox_path: str) -> FileMetadata:
        """
        Upload un fichier par chunks (pour fichiers > 4MB).
        
        Args:
            file_content: Contenu du fichier en bytes
            dropbox_path: Chemin Dropbox du fichier
            
        Returns:
            FileMetadata du fichier uploadé
        """
        file_size = len(file_content)
        
        # Démarrer une session d'upload
        session_start_result = self.dbx.files_upload_session_start(
            file_content[:self.CHUNK_SIZE]
        )
        session_id = session_start_result.session_id
        offset = self.CHUNK_SIZE
        
        # Uploader les chunks intermédiaires
        while offset < file_size:
            chunk_size = min(self.CHUNK_SIZE, file_size - offset)
            
            if offset + chunk_size < file_size:
                # Chunk intermédiaire
                self.dbx.files_upload_session_append_v2(
                    file_content[offset:offset + chunk_size],
                    session_id=session_id,
                    offset=offset
                )
            else:
                # Dernier chunk
                commit_info = {
                    'path': dropbox_path,
                    'mode': WriteMode('overwrite'),
                    'autorename': False,
                    'mute': False
                }
                
                result = self.dbx.files_upload_session_finish(
                    file_content[offset:offset + chunk_size],
                    session_id=session_id,
                    offset=offset,
                    commit=commit_info
                )
                
                logger.debug(f"Chunked upload completed for {dropbox_path}")
                return result
            
            offset += chunk_size
            logger.debug(f"Uploaded chunk: {offset}/{file_size} bytes")
    
    def download_file(self, file_id: str) -> bytes:
        """
        Télécharge un fichier depuis Dropbox.
        
        Args:
            file_id: ID ou path du fichier Dropbox
            
        Returns:
            Contenu du fichier en bytes
        """
        try:
            # Dropbox utilise les paths, pas les IDs pour download
            # Si file_id ressemble à un path, l'utiliser directement
            path = file_id if file_id.startswith('/') else f'/{file_id}'
            
            metadata, response = self.dbx.files_download(path)
            content = response.content
            
            logger.info(f"File downloaded from Dropbox: {path}")
            return content
            
        except ApiError as e:
            logger.error(f"Dropbox download failed for file {file_id}: {e}")
            raise Exception(f"Dropbox API error: {str(e)}")
        except Exception as e:
            logger.error(f"Dropbox download failed: {e}")
            raise
    
    def delete_file(self, file_id: str) -> bool:
        """
        Supprime un fichier de Dropbox.
        
        Args:
            file_id: ID ou path du fichier à supprimer
            
        Returns:
            True si suppression réussie
        """
        try:
            path = file_id if file_id.startswith('/') else f'/{file_id}'
            
            self.dbx.files_delete_v2(path)
            
            logger.info(f"File deleted from Dropbox: {path}")
            return True
            
        except ApiError as e:
            logger.error(f"Dropbox delete failed for file {file_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Dropbox delete failed: {e}")
            return False
    
    def get_file_info(self, file_id: str) -> Dict[str, any]:
        """
        Récupère les informations d'un fichier.
        
        Args:
            file_id: ID ou path du fichier
            
        Returns:
            Dict contenant name, size, modified_time, etc.
        """
        try:
            path = file_id if file_id.startswith('/') else f'/{file_id}'
            
            metadata = self.dbx.files_get_metadata(path)
            
            return {
                'id': metadata.id,
                'name': metadata.name,
                'size': getattr(metadata, 'size', 0),
                'path': metadata.path_display,
                'modified_time': metadata.server_modified.isoformat() if hasattr(metadata, 'server_modified') else None,
                'is_folder': isinstance(metadata, FolderMetadata),
            }
            
        except ApiError as e:
            logger.error(f"Failed to get file info for {file_id}: {e}")
            raise Exception(f"Dropbox API error: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to get file info: {e}")
            raise
    
    def list_files(self, folder_id: Optional[str] = None, path: Optional[str] = None) -> List[Dict[str, any]]:
        """
        Liste les fichiers d'un dossier.
        
        Args:
            folder_id: Non utilisé pour Dropbox
            path: Chemin du dossier
            
        Returns:
            Liste de dicts avec infos des fichiers
        """
        try:
            folder_path = path if path else ''
            if folder_path and not folder_path.startswith('/'):
                folder_path = f'/{folder_path}'
            
            # Liste les entrées du dossier
            result = self.dbx.files_list_folder(folder_path or '')
            
            files = []
            for entry in result.entries:
                files.append({
                    'id': entry.id,
                    'name': entry.name,
                    'size': getattr(entry, 'size', 0),
                    'path': entry.path_display,
                    'modified_time': entry.server_modified.isoformat() if hasattr(entry, 'server_modified') else None,
                    'is_folder': isinstance(entry, FolderMetadata),
                })
            
            return files
            
        except ApiError as e:
            logger.error(f"Failed to list files in {path}: {e}")
            raise Exception(f"Dropbox API error: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to list files: {e}")
            raise
    
    def create_folder(self, name: str, parent_id: Optional[str] = None, parent_path: Optional[str] = None) -> Dict[str, any]:
        """
        Crée un dossier dans Dropbox.
        
        Args:
            name: Nom du dossier
            parent_id: Non utilisé pour Dropbox
            parent_path: Chemin du parent
            
        Returns:
            Dict contenant folder_id, name, path
        """
        try:
            if parent_path:
                folder_path = f"/{parent_path.strip('/')}/{name}".replace('//', '/')
            else:
                folder_path = f'/{name}'
            
            result = self.dbx.files_create_folder_v2(folder_path, autorename=False)
            folder = result.metadata
            
            logger.info(f"Folder created in Dropbox: {folder.name} (ID: {folder.id})")
            
            return {
                'folder_id': folder.id,
                'name': folder.name,
                'path': folder.path_display,
            }
            
        except ApiError as e:
            # Si le dossier existe déjà, récupérer ses infos
            if hasattr(e.error, 'create_folder') and e.error.is_path():
                try:
                    existing = self.dbx.files_get_metadata(folder_path)
                    return {
                        'folder_id': existing.id,
                        'name': existing.name,
                        'path': existing.path_display,
                    }
                except:
                    pass
            
            logger.error(f"Failed to create folder {name}: {e}")
            raise Exception(f"Dropbox API error: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to create folder: {e}")
            raise
    
    def get_quota_info(self) -> Dict[str, any]:
        """
        Récupère les informations de quota/espace disponible.
        
        Returns:
            Dict contenant total_space, used_space, available_space (en bytes)
        """
        try:
            space_usage = self.dbx.users_get_space_usage()
            
            # Allocation peut être individuelle ou team
            if hasattr(space_usage.allocation, 'get_individual'):
                allocated = space_usage.allocation.get_individual().allocated
            elif hasattr(space_usage.allocation, 'get_team'):
                allocated = space_usage.allocation.get_team().allocated
            else:
                allocated = 0
            
            used = space_usage.used
            
            return {
                'total_space': allocated,
                'used_space': used,
                'available_space': allocated - used if allocated > 0 else 0,
            }
            
        except ApiError as e:
            logger.error(f"Failed to get quota info: {e}")
            raise Exception(f"Dropbox API error: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to get quota info: {e}")
            raise
    
    def get_share_link(self, file_id: str, expires: Optional[int] = None) -> str:
        """
        Génère un lien de partage pour un fichier.
        
        Args:
            file_id: ID ou path du fichier
            expires: Non supporté par Dropbox
            
        Returns:
            URL de partage
        """
        try:
            path = file_id if file_id.startswith('/') else f'/{file_id}'
            
            # Essayer de créer un lien de partage
            try:
                link = self.dbx.sharing_create_shared_link_with_settings(path)
                return link.url
            except ApiError as e:
                # Si le lien existe déjà, le récupérer
                if hasattr(e.error, 'shared_link_already_exists'):
                    links = self.dbx.sharing_list_shared_links(path=path)
                    if links.links:
                        return links.links[0].url
                raise
            
        except Exception as e:
            logger.error(f"Failed to create share link for {file_id}: {e}")
            # Retourner une URL vide plutôt que de crasher
            return ''
