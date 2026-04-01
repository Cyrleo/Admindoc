# =============================================================================
# ADMINDOC - CLOUD STORAGE CONFIGURATION
# =============================================================================
# Guide pour activer le stockage cloud multi-provider (Google Drive, OneDrive, Dropbox)
#
# Documentation: /home/leo/.copilot/session-state/3ae1839c-f3b9-40c4-b712-6813b96ece9f/plan.md
# =============================================================================

# Cloud Storage - Global
CLOUD_STORAGE_ENABLED=true

# ⚠️ IMPORTANT: Générer une clé de chiffrement sécurisée
# Exécuter: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
CLOUD_STORAGE_ENCRYPTION_KEY=

# -----------------------------------------------------------------------------
# Google Drive OAuth Configuration
# -----------------------------------------------------------------------------
# 1. Créer un projet sur Google Cloud Console: https://console.cloud.google.com
# 2. Activer l'API Google Drive
# 3. Créer des identifiants OAuth 2.0 (Type: Application Web)
# 4. Ajouter l'URI de redirection: http://localhost:8000/api/cloud-storage/oauth/callback/google/
#    (En production, utiliser votre domaine HTTPS)

GOOGLE_DRIVE_CLIENT_ID=
GOOGLE_DRIVE_CLIENT_SECRET=
GOOGLE_DRIVE_REDIRECT_URI=http://localhost:8000/api/cloud-storage/oauth/callback/google/

# -----------------------------------------------------------------------------
# Microsoft OneDrive OAuth Configuration (En développement)
# -----------------------------------------------------------------------------
# 1. Enregistrer une application sur Azure Portal: https://portal.azure.com
# 2. Aller dans "Azure Active Directory" > "App registrations" > "New registration"
# 3. Configurer l'URI de redirection: http://localhost:8000/api/cloud-storage/oauth/callback/onedrive/
# 4. Créer un secret client dans "Certificates & secrets"

ONEDRIVE_CLIENT_ID=
ONEDRIVE_CLIENT_SECRET=
ONEDRIVE_REDIRECT_URI=http://localhost:8000/api/cloud-storage/oauth/callback/onedrive/

# -----------------------------------------------------------------------------
# Dropbox OAuth Configuration (En développement)
# -----------------------------------------------------------------------------
# 1. Créer une app sur Dropbox App Console: https://www.dropbox.com/developers/apps
# 2. Choisir "Scoped access" et "Full Dropbox"
# 3. Ajouter l'URI de redirection: http://localhost:8000/api/cloud-storage/oauth/callback/dropbox/

DROPBOX_APP_KEY=
DROPBOX_APP_SECRET=
DROPBOX_REDIRECT_URI=http://localhost:8000/api/cloud-storage/oauth/callback/dropbox/

# =============================================================================
# ÉTAPES D'INITIALISATION
# =============================================================================
#
# 1. Installer les dépendances (déjà fait si vous lisez ceci):
#    pip install -r requirements.txt
#
# 2. Générer la clé de chiffrement:
#    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
#    Copier le résultat dans CLOUD_STORAGE_ENCRYPTION_KEY
#
# 3. Appliquer les migrations:
#    python manage.py migrate
#
# 4. Initialiser les providers:
#    python scripts/init_cloud_providers.py
#
# 5. (Optionnel) Configurer les credentials OAuth pour Google Drive
#
# 6. Redémarrer le serveur Django
#
# =============================================================================
# UTILISATION
# =============================================================================
#
# Frontend:
# 1. GET /api/cloud-storage/providers/ - Liste des providers disponibles
# 2. POST /api/cloud-storage/oauth/initiate/ - Initier connexion OAuth
#    Body: { "provider_id": 1, "display_name": "Mon Google Drive" }
# 3. Rediriger l'utilisateur vers l'URL OAuth retournée
# 4. Après autorisation, l'utilisateur est redirigé vers /api/cloud-storage/oauth/callback/{provider}/
# 5. GET /api/cloud-storage/connections/ - Liste des connexions cloud de l'utilisateur
#
# Upload vers cloud:
# POST /api/documents/files/move-to-cloud/{file_id}/
# Body: { "target_storage_id": 1, "delete_source": false }
#
# Télécharger depuis cloud:
# POST /api/documents/files/move-to-local/{file_id}/
# Body: { "delete_source": false }
#
# =============================================================================
