# Changelog

## [Unreleased]

### Added - Cloud Storage Multi-Provider (Complete Implementation)

#### Infrastructure
- Modèles de données pour cloud storage (CloudStorageProvider, UserCloudStorage, CloudStorageActivity)
- Système de chiffrement Fernet pour tokens OAuth (cors/utils/encryption.py)
- Factory pattern pour backends cloud (cors/storage/factory.py)
- Token refresh automatique (cors/storage/token_manager.py)
- Interface abstraite BaseCloudStorageBackend pour extensibilité
- Auto-registration des backends via __init__.py

#### Backends Cloud (3 Providers Complets)
- **Google Drive Backend** (cors/storage/backends/google_drive.py)
  - OAuth 2.0 flow avec Google
  - Upload/Download/Delete fichiers
  - Upload resumable pour gros fichiers
  - Gestion dossiers et paths automatiques
  - Récupération quota et informations compte
  - Génération liens de partage
  
- **OneDrive Backend** (cors/storage/backends/onedrive.py)
  - OAuth 2.0 MSAL flow (Microsoft Graph API)
  - Upload simple (<4MB) et chunked (10MB chunks)
  - Download/Delete fichiers et dossiers
  - Création dossiers automatique
  - Récupération quota OneDrive
  - Liens de partage temporaires
  
- **Dropbox Backend** (cors/storage/backends/dropbox.py)
  - OAuth 2.0 flow (long-lived tokens)
  - Upload simple et chunked (4MB chunks)
  - Download/Delete fichiers
  - Gestion dossiers
  - Récupération quota Dropbox
  - Génération liens de partage

#### Uploads Asynchrones (Celery)
- Tâche upload_file_to_cloud_task (async upload avec retry)
- Tâche sync_quota_task (synchronisation périodique quotas)
- Tâche cleanup_orphaned_cloud_files_task (nettoyage hebdomadaire)
- Configuration Celery Beat pour tâches périodiques
- Support upload sync/async dans API

#### API REST Endpoints
- Endpoints providers cloud (liste, détails)
- Endpoints connexions cloud (CRUD complet)
- Actions sur connexions (disconnect, sync_quota, set_default, test_connection)
- OAuth flow complet pour 3 providers (initiate + callbacks)
- Transfert fichiers local ↔ cloud (sync/async)
- Historique des activités cloud

#### Configuration
- Variables environnement cloud storage (settings.py)
- Support OAuth Google Drive, OneDrive, Dropbox
- Feature flag CLOUD_STORAGE_ENABLED
- Clé de chiffrement CLOUD_STORAGE_ENCRYPTION_KEY
- URLs de redirection OAuth pour 3 providers

#### Scripts & Documentation
- Script d'initialisation providers (scripts/init_cloud_providers.py)
- Guide de configuration (CLOUD_STORAGE_CONFIG.md)
- Documentation technique (CLOUD_STORAGE_README.md)
- Synthèse d'implémentation complète (IMPLEMENTATION_SUMMARY.md)
- .env.example mis à jour

#### Dépendances
- cryptography==44.0.0 (chiffrement tokens)
- google-auth==2.36.0
- google-auth-oauthlib==1.2.1
- google-auth-httplib2==0.2.0
- google-api-python-client==2.156.0
- msal==1.31.1 (OneDrive)
- dropbox==12.0.2 (Dropbox)

### Changed
- DocumentFile model étendu avec champs cloud storage
- cors/pages/cloud_storage/urls.py avec routes OAuth
- requirements.txt avec dépendances cloud

### Fixed
- Bug ligne 297 views.py : document.document_type.name → document.category.name

### Security
- Chiffrement automatique tokens OAuth avec Fernet
- Refresh automatique tokens avant expiration
- CSRF protection avec states OAuth
- Scopes minimaux par provider

## [Previous entries remain unchanged] - Améliorations du Projet AdminDoc

## 🎯 Améliorations Implémentées (31 Mars 2026)

### 1. ✅ Upload Multi-Fichiers pour Documents

**Problème**: Un document ne pouvait avoir qu'un seul fichier attaché.

**Solution**: Nouveau système permettant d'uploader plusieurs fichiers par document.

#### Architecture
- Nouveau modèle `DocumentFile` pour gérer plusieurs fichiers par document
- Relation: `Document` (1) → `DocumentFile` (N)
- Support de tous types de fichiers: images, PDF, Word, Excel, etc.

#### Utilisation

**Upload de plusieurs fichiers:**
```bash
curl -X POST http://localhost:8000/api/documents/upload-local/ \
  -H "Authorization: Bearer <TOKEN>" \
  -F "title=Acte de Naissance" \
  -F "description=Scans multiples du document" \
  -F "files=@scan_recto.jpg" \
  -F "files=@scan_verso.jpg" \
  -F "files=@document.pdf"
```

**Réponse:**
```json
{
  "id": 1,
  "title": "Acte de Naissance",
  "files": [
    {
      "id": 1,
      "file": "http://localhost:8000/media/document_files/2026/03/31/scan_recto.jpg",
      "file_name": "scan_recto.jpg",
      "mime_type": "image/jpeg",
      "size": 245632,
      "is_primary": true,
      "uploaded_at": "2026-03-31T08:30:35Z"
    },
    {
      "id": 2,
      "file": "http://localhost:8000/media/document_files/2026/03/31/scan_verso.jpg",
      "file_name": "scan_verso.jpg",
      "mime_type": "image/jpeg",
      "size": 238941,
      "is_primary": false,
      "uploaded_at": "2026-03-31T08:30:36Z"
    },
    {
      "id": 3,
      "file": "http://localhost:8000/media/document_files/2026/03/31/document.pdf",
      "file_name": "document.pdf",
      "mime_type": "application/pdf",
      "size": 512000,
      "is_primary": false,
      "uploaded_at": "2026-03-31T08:30:37Z"
    }
  ]
}
```

#### Endpoints

**1. Télécharger le fichier principal d'un document:**
```bash
GET /api/documents/{id}/download/
```
Retourne le fichier marqué comme `is_primary`, ou le premier fichier si aucun n'est marqué.

**2. Télécharger un fichier spécifique:**
```bash
GET /api/documents/files/{file_id}/download/
```
Retourne un fichier spécifique par son ID.

#### Caractéristiques
- ✅ Premier fichier uploadé automatiquement marqué comme `is_primary`
- ✅ Détection automatique du type MIME
- ✅ Validation de taille (max 50MB par fichier)
- ✅ Support de tous types de fichiers
- ✅ Rétrocompatibilité avec l'ancien champ `file` (deprecated)

---

### 2. ✅ Correction Endpoint /me

**Problème**: L'endpoint `/auth/users/me/` ne retournait pas `first_name` et `last_name`.

**Solution**: Création d'un serializer personnalisé pour Djoser.

#### Utilisation

**Requête:**
```bash
curl -X GET http://localhost:8000/auth/users/me/ \
  -H "Authorization: Bearer <TOKEN>"
```

**Réponse:**
```json
{
  "id": 1,
  "email": "user@example.com",
  "first_name": "Jean",
  "last_name": "Dupont",
  "is_staff": false,
  "is_active": true,
  "date_joined": "2026-03-31T08:00:00Z",
  "is_verified": false
}
```

#### Changements Techniques
- Nouveau fichier `accounts/serializers.py` avec:
  - `UserSerializer`: Pour les opérations de lecture (GET /auth/users/me/)
  - `UserCreateSerializer`: Pour l'inscription
- Configuration DJOSER mise à jour dans `settings.py`

---

### 3. ✅ Améliorations Supplémentaires

#### Validation des Fichiers
- Limite de taille par fichier: **50 MB**
- Validation du nombre minimum de fichiers (au moins 1 requis)
- Messages d'erreur clairs en cas de dépassement

#### Documentation API
- Schéma OpenAPI mis à jour automatiquement
- Documentation Swagger accessible: `http://localhost:8000/api/docs/`
- Documentation ReDoc accessible: `http://localhost:8000/api/redoc/`

#### Audit et Logging
- Nouveau type d'action: `download_document_file`
- Métadonnées enrichies dans les logs (file_name, document_id)

---

## 📋 Modèle DocumentFile

```python
class DocumentFile(models.Model):
    document = ForeignKey(Document)       # Document parent
    file = FileField(...)                 # Fichier uploadé
    file_name = CharField(512)            # Nom original
    mime_type = CharField(100)            # Type MIME
    size = PositiveBigIntegerField()      # Taille en bytes
    is_primary = BooleanField()           # Fichier principal?
    uploaded_at = DateTimeField()         # Date d'upload
    created_at = DateTimeField()
    updated_at = DateTimeField()
```

---

## 🔄 Migration des Données

Un script de migration a été créé pour transférer les fichiers existants:
```bash
python manage.py shell < scripts/migrate_document_files.py
```

Les fichiers existants dans le champ `Document.file` sont automatiquement migrés vers `DocumentFile` avec `is_primary=True`.

---

## 🚀 Déploiement

### Étapes de Migration

1. **Créer l'environnement virtuel** (si nécessaire):
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Appliquer les migrations**:
   ```bash
   python manage.py migrate
   ```

3. **Migrer les données existantes** (si vous avez des fichiers):
   ```bash
   python scripts/migrate_document_files.py
   ```

4. **Tester**:
   ```bash
   python manage.py runserver
   ```

---

## 📊 Tests Effectués

✅ Upload de 3 fichiers pour un document  
✅ Téléchargement du fichier principal  
✅ Téléchargement d'un fichier spécifique  
✅ Endpoint `/auth/users/me/` retourne first_name et last_name  
✅ Validation des fichiers trop volumineux  
✅ Détection automatique du MIME type  
✅ Documentation OpenAPI générée correctement  

---

## 🔧 Rétrocompatibilité

Les anciens champs du modèle `Document` sont conservés mais marqués comme **DEPRECATED**:
- `file` (FileField) → Utilisez `DocumentFile` à la place
- `file_name` (CharField)
- `mime_type` (CharField)
- `size` (BigIntegerField)

Ces champs peuvent être supprimés dans une future version majeure.

---

## 📝 Notes Importantes

- L'endpoint upload accepte maintenant `files` (liste) au lieu de `file` (unique)
- Le premier fichier uploadé est automatiquement marqué comme `is_primary`
- Limite par fichier: 50 MB (configurable dans le serializer)
- Les fichiers sont stockés dans `media/document_files/%Y/%m/%d/`
- L'ancien dossier `media/documents/` est conservé pour compatibilité

---

## 🎓 Exemples d'Usage

### Upload avec catégorie et tags
```bash
curl -X POST http://localhost:8000/api/documents/upload-local/ \
  -H "Authorization: Bearer <TOKEN>" \
  -F "title=Passeport" \
  -F "description=Passeport français" \
  -F "category=5" \
  -F "tags=10,11" \
  -F "date_expiration=2030-12-31" \
  -F "files=@passeport_photo.jpg" \
  -F "files=@passeport_scan.pdf"
```

### Récupérer un document avec ses fichiers
```bash
curl -X GET http://localhost:8000/api/documents/1/ \
  -H "Authorization: Bearer <TOKEN>"
```

### Lister tous les documents
```bash
curl -X GET http://localhost:8000/api/documents/ \
  -H "Authorization: Bearer <TOKEN>"
```

---

Développé avec ❤️ par GitHub Copilot CLI
