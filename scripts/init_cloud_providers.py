#!/usr/bin/env python
"""
Script pour initialiser les providers de stockage cloud par défaut.
À exécuter après les migrations.

Usage:
    python scripts/init_cloud_providers.py
"""

import os
import sys
import django

# Setup Django environment
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'doc.settings')
django.setup()

from cors.models import CloudStorageProvider


def init_cloud_providers():
    """Crée ou met à jour les providers de stockage cloud par défaut."""
    
    providers = [
        {
            'code': CloudStorageProvider.PROVIDER_GOOGLE_DRIVE,
            'name': 'Google Drive',
            'icon': 'google-drive',
            'is_active': True,
            'requires_oauth': True,
            'api_base_url': 'https://www.googleapis.com/drive/v3',
            'oauth_authorize_url': 'https://accounts.google.com/o/oauth2/auth',
            'oauth_token_url': 'https://oauth2.googleapis.com/token',
            'scopes': [
                'https://www.googleapis.com/auth/drive.file',
                'https://www.googleapis.com/auth/drive.metadata.readonly',
                'https://www.googleapis.com/auth/userinfo.email',
                'https://www.googleapis.com/auth/userinfo.profile',
            ],
            'config': {
                'max_file_size': 5368709120,  # 5 GB
                'supported_mime_types': ['*/*'],
            }
        },
        {
            'code': CloudStorageProvider.PROVIDER_ONEDRIVE,
            'name': 'Microsoft OneDrive',
            'icon': 'onedrive',
            'is_active': False,  # Désactivé jusqu'à implémentation complète
            'requires_oauth': True,
            'api_base_url': 'https://graph.microsoft.com/v1.0',
            'oauth_authorize_url': 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize',
            'oauth_token_url': 'https://login.microsoftonline.com/common/oauth2/v2.0/token',
            'scopes': [
                'Files.ReadWrite',
                'User.Read',
                'offline_access',
            ],
            'config': {
                'max_file_size': 268435456000,  # 250 GB (avec chunks)
                'chunk_size': 10485760,  # 10 MB
            }
        },
        {
            'code': CloudStorageProvider.PROVIDER_DROPBOX,
            'name': 'Dropbox',
            'icon': 'dropbox',
            'is_active': False,  # Désactivé jusqu'à implémentation complète
            'requires_oauth': True,
            'api_base_url': 'https://api.dropboxapi.com/2',
            'oauth_authorize_url': 'https://www.dropbox.com/oauth2/authorize',
            'oauth_token_url': 'https://api.dropboxapi.com/oauth2/token',
            'scopes': [
                'files.content.write',
                'files.content.read',
                'account_info.read',
            ],
            'config': {
                'max_file_size': 53687091200,  # 50 GB
                'chunk_size': 4194304,  # 4 MB
            }
        },
        {
            'code': CloudStorageProvider.PROVIDER_LOCAL,
            'name': 'Serveur Local',
            'icon': 'server',
            'is_active': True,
            'requires_oauth': False,
            'api_base_url': '',
            'oauth_authorize_url': '',
            'oauth_token_url': '',
            'scopes': [],
            'config': {
                'is_default': True,
            }
        },
    ]
    
    created_count = 0
    updated_count = 0
    
    for provider_data in providers:
        code = provider_data['code']
        
        provider, created = CloudStorageProvider.objects.update_or_create(
            code=code,
            defaults=provider_data
        )
        
        if created:
            created_count += 1
            print(f"✅ Provider créé: {provider.name} ({provider.code})")
        else:
            updated_count += 1
            print(f"🔄 Provider mis à jour: {provider.name} ({provider.code})")
    
    print(f"\n✨ Initialisation terminée:")
    print(f"   - {created_count} provider(s) créé(s)")
    print(f"   - {updated_count} provider(s) mis à jour")
    print(f"\n📝 Providers actifs:")
    
    active_providers = CloudStorageProvider.objects.filter(is_active=True)
    for provider in active_providers:
        status = "🟢 Implémenté" if provider.code == CloudStorageProvider.PROVIDER_GOOGLE_DRIVE else "⚪ Par défaut" if provider.code == CloudStorageProvider.PROVIDER_LOCAL else "🟡 En développement"
        print(f"   - {provider.name}: {status}")


if __name__ == '__main__':
    print("🚀 Initialisation des providers de stockage cloud...")
    print()
    
    try:
        init_cloud_providers()
    except Exception as e:
        print(f"\n❌ Erreur lors de l'initialisation: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
