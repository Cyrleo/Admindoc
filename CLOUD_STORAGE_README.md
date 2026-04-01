# 📦 Cloud Storage Multi-Provider - Guide d'Implémentation

## ✅ Implémentation Actuelle (Phase 1 & 2 complètes)

### 🎯 Fonctionnalités Disponibles

- ✅ **Infrastructure complète**
  - Modèles de données (CloudStorageProvider, UserCloudStorage, CloudStorageActivity)
  - Chiffrement des tokens OAuth (Fernet)
  - Factory pattern pour backends
  - Token refresh automatique

- ✅ **Backend Google Drive fonctionnel**
  - OAuth 2.0 flow complet
  - Upload/Download/Delete fichiers
  - Gestion des dossiers
  - Récupération quota
  - Partage de liens

- ✅ **API REST endpoints**
  - Liste des providers disponibles
  - Gestion des connexions cloud (CRUD)
  - Transfert fichiers local ↔ cloud
  - Historique des activités
  - Endpoints OAuth (initiate + callbacks)

## 🚀 Installation et Configuration

### 1. Dépendances

```bash
pip install -r requirements.txt
```

Les dépendances cloud sont déjà dans `requirements.txt` :
- `cryptography` - Chiffrement tokens
- `google-api-python-client`, `google-auth`, `google-auth-oauthlib` - Google Drive
- `msal` - OneDrive (à venir)
- `dropbox` - Dropbox (à venir)

### 2. Générer la clé de chiffrement

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copier le résultat dans `.env` :
```env
CLOUD_STORAGE_ENCRYPTION_KEY=<votre_clé_générée>
```

### 3. Configuration Google Drive (Optionnel)

1. **Créer un projet Google Cloud** : https://console.cloud.google.com
2. **Activer Google Drive API** :
   - Dans le projet, aller à "APIs & Services" > "Library"
   - Chercher "Google Drive API" et l'activer
3. **Créer des identifiants OAuth 2.0** :
   - "APIs & Services" > "Credentials" > "Create Credentials" > "OAuth client ID"
   - Type d'application : "Application Web"
   - URI de redirection autorisée : `http://localhost:8000/api/cloud-storage/oauth/callback/google/`
   - (En production, utiliser votre domaine HTTPS)
4. **Copier les credentials** dans `.env` :
   ```env
   GOOGLE_DRIVE_CLIENT_ID=<votre_client_id>
   GOOGLE_DRIVE_CLIENT_SECRET=<votre_secret>
   ```

### 4. Appliquer les migrations

```bash
python manage.py migrate
```

### 5. Initialiser les providers

```bash
python scripts/init_cloud_providers.py
```

Ce script crée les providers par défaut :
- Google Drive (actif)
- OneDrive (inactif, en développement)
- Dropbox (inactif, en développement)
- Serveur Local (actif par défaut)

## 📡 Utilisation de l'API

### Lister les providers disponibles

```bash
GET /api/cloud-storage/providers/
```

**Réponse** :
```json
[
  {
    "id": 1,
    "code": "google_drive",
    "name": "Google Drive",
    "icon": "google-drive",
    "is_active": true,
    "requires_oauth": true,
    "created_at": "2026-04-01T14:00:00Z"
  }
]
```

### Connecter Google Drive

**1. Initier OAuth**

```bash
POST /api/cloud-storage/oauth/initiate/
Authorization: Bearer <token_jwt>
Content-Type: application/json

{
  "provider_id": 1,
  "display_name": "Mon Google Drive Perso"
}
```

**Réponse** :
```json
{
  "oauth_url": "https://accounts.google.com/o/oauth2/auth?...",
  "state": "abc123...",
  "provider": {
    "id": 1,
    "code": "google_drive",
    "name": "Google Drive"
  }
}
```

**2. Rediriger l'utilisateur**

Frontend doit rediriger vers `oauth_url` retournée.

**3. Callback automatique**

Après autorisation, Google redirige vers :
```
/api/cloud-storage/oauth/callback/google/?code=...&state=...
```

Le backend finalise automatiquement la connexion.

### Lister les connexions cloud

```bash
GET /api/cloud-storage/connections/
Authorization: Bearer <token_jwt>
```

**Réponse** :
```json
[
  {
    "id": 1,
    "provider": {
      "id": 1,
      "code": "google_drive",
      "name": "Google Drive"
    },
    "cloud_account_email": "user@gmail.com",
    "display_name": "Mon Google Drive Perso",
    "is_default": true,
    "is_active": true,
    "total_space": 16106127360,
    "used_space": 5000000000,
    "available_space": 11106127360,
    "last_sync": "2026-04-01T15:00:00Z",
    "created_at": "2026-04-01T14:30:00Z"
  }
]
```

### Déplacer un fichier vers le cloud

```bash
POST /api/documents/files/move-to-cloud/{file_id}/
Authorization: Bearer <token_jwt>
Content-Type: application/json

{
  "target_storage_id": 1,
  "delete_source": false
}
```

**Réponse** :
```json
{
  "message": "File moved to cloud successfully",
  "file": {
    "id": 42,
    "storage_type": "cloud",
    "cloud_storage": "Mon Google Drive Perso",
    "sync_status": "synced"
  }
}
```

### Rapatrier un fichier en local

```bash
POST /api/documents/files/move-to-local/{file_id}/
Authorization: Bearer <token_jwt>
Content-Type: application/json

{
  "delete_source": false
}
```

### Synchroniser le quota

```bash
POST /api/cloud-storage/connections/{id}/sync_quota/
Authorization: Bearer <token_jwt>
```

### Déconnecter un cloud storage

```bash
POST /api/cloud-storage/connections/{id}/disconnect/
Authorization: Bearer <token_jwt>
```

## 🔐 Sécurité

- **Tokens chiffrés** : Tous les tokens OAuth sont chiffrés avec Fernet avant stockage en base
- **Refresh automatique** : Les tokens sont rafraîchis automatiquement 5 minutes avant expiration
- **CSRF Protection** : Les states OAuth sont générés aléatoirement et validés
- **HTTPS requis** : En production, tous les OAuth callbacks doivent être en HTTPS
- **Scopes minimaux** : Seulement les permissions nécessaires sont demandées

## 🏗️ Architecture

```
cors/
├── models.py                          # Modèles CloudStorageProvider, UserCloudStorage, etc.
├── storage/
│   ├── __init__.py                    # Auto-registration backends
│   ├── factory.py                     # CloudStorageFactory
│   ├── token_manager.py               # TokenManager (auto-refresh)
│   └── backends/
│       ├── __init__.py                # Registration des backends
│       ├── base.py                    # BaseCloudStorageBackend (interface)
│       └── google_drive.py            # GoogleDriveBackend ✅
├── pages/cloud_storage/
│   ├── views.py                       # API ViewSets
│   ├── oauth_views.py                 # OAuth flow (initiate + callbacks)
│   ├── serializers.py                 # Serializers
│   └── urls.py                        # URLs routing
└── utils/
    └── encryption.py                  # TokenEncryption (Fernet)
```

## 🚧 Prochaines Étapes (Phase 3+)

### Phase 3 : OneDrive Backend
- [ ] Implémenter `OneDriveBackend` avec Microsoft Graph API
- [ ] OAuth MSAL flow
- [ ] Tests d'intégration

### Phase 4 : Dropbox Backend
- [ ] Implémenter `DropboxBackend`
- [ ] Support chunked uploads pour gros fichiers
- [ ] Tests d'intégration

### Phase 5 : Upload Asynchrone
- [ ] Tâches Celery pour uploads cloud
- [ ] Progress tracking
- [ ] Webhooks notifications

### Phase 6 : Améliorations
- [ ] Cache des URLs de partage
- [ ] Thumbnails/previews
- [ ] Synchronisation bidirectionnelle
- [ ] Gestion des conflits

## 🐛 Bugs Corrigés

- ✅ **Bug document_type** : Ligne 297 de `views.py` référençait `document.document_type` qui n'existe pas
  - **Solution** : Utiliser `document.category.name` à la place

## 📝 Notes Techniques

### Providers supportés
- **Google Drive** : 15 GB gratuit, API v3 ✅ **FONCTIONNEL**
- **OneDrive** : 5 GB gratuit, Microsoft Graph API 🚧 **EN DÉVELOPPEMENT**
- **Dropbox** : 2 GB gratuit, Dropbox SDK 🚧 **EN DÉVELOPPEMENT**

### Limitations actuelles
- Pas de webhooks (synchronisation manuelle uniquement)
- Pas de gestion des conflits pour sync bidirectionnelle
- States OAuth stockés en mémoire (utiliser Redis en production)

### Environnement de test
Pour tester sans configurer OAuth :
1. Provider "Serveur Local" disponible par défaut
2. Utilise le stockage Django FileField standard
3. Pas d'OAuth requis

## 🆘 Dépannage

### Erreur "No module named 'google'"
```bash
pip install google-api-python-client google-auth google-auth-oauthlib
```

### Erreur "Invalid encryption key"
Générer une nouvelle clé :
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Token refresh failed
- Vérifier que les credentials OAuth sont corrects
- Vérifier que l'application OAuth n'est pas révoquée côté Google
- Tester la connexion : `GET /api/cloud-storage/connections/{id}/test_connection/`

## 📚 Ressources

- [Google Drive API v3](https://developers.google.com/drive/api/v3/about-sdk)
- [Microsoft Graph API](https://learn.microsoft.com/en-us/graph/api/overview)
- [Dropbox SDK](https://www.dropbox.com/developers/documentation/python)
- [Fernet Encryption](https://cryptography.io/en/latest/fernet/)

---

**Auteur** : GitHub Copilot CLI  
**Date** : 2026-04-01  
**Version** : 1.0.0 (Google Drive fonctionnel)
