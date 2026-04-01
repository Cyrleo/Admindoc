# 🚀 Guide de Déploiement Rapide - Cloud Storage

## ✅ Statut du Projet

**IMPLÉMENTATION TERMINÉE À 100%** pour les phases demandées :
- ✅ Backend OneDrive (Phase 3)
- ✅ Backend Dropbox (Phase 4)
- ✅ Uploads Asynchrones Celery (Phase 5)

---

## 📋 Checklist de Déploiement

### 1️⃣ Vérification des Fichiers

Vérifiez que les fichiers suivants existent :

```bash
# Backends
cors/storage/backends/google_drive.py    ✅
cors/storage/backends/onedrive.py        ✅
cors/storage/backends/dropbox.py         ✅

# Tâches Celery
cors/tasks.py                            ✅ (modifié avec 3 nouvelles tâches)

# OAuth
cors/pages/cloud_storage/oauth_views.py  ✅

# Documentation
FINAL_DELIVERY_SUMMARY.md                ✅
CLOUD_STORAGE_README.md                  ✅
CLOUD_STORAGE_CONFIG.md                  ✅
```

### 2️⃣ Installation des Dépendances

```bash
# Activer l'environnement virtuel
source venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt

# Vérifier l'installation
pip list | grep -E "google|msal|dropbox|crypto"
```

**Packages requis** :
- cryptography==44.0.0
- google-auth, google-auth-oauthlib, google-api-python-client
- msal==1.31.1
- dropbox==12.0.2

### 3️⃣ Configuration OAuth

#### Générer la clé de chiffrement

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

#### Créer le fichier `.env`

Copiez `.env.example` vers `.env` et remplissez :

```bash
# Encryption (OBLIGATOIRE)
CLOUD_STORAGE_ENCRYPTION_KEY=<clé générée ci-dessus>

# Google Drive OAuth (optionnel si vous n'utilisez que OneDrive/Dropbox)
GOOGLE_DRIVE_CLIENT_ID=votre-client-id
GOOGLE_DRIVE_CLIENT_SECRET=votre-secret
GOOGLE_DRIVE_REDIRECT_URI=http://localhost:8000/api/cloud-storage/oauth/callback/google/

# OneDrive OAuth
ONEDRIVE_CLIENT_ID=votre-client-id
ONEDRIVE_CLIENT_SECRET=votre-secret
ONEDRIVE_REDIRECT_URI=http://localhost:8000/api/cloud-storage/oauth/callback/onedrive/

# Dropbox OAuth
DROPBOX_APP_KEY=votre-app-key
DROPBOX_APP_SECRET=votre-app-secret
DROPBOX_REDIRECT_URI=http://localhost:8000/api/cloud-storage/oauth/callback/dropbox/
```

📖 **Voir `CLOUD_STORAGE_CONFIG.md` pour créer les apps OAuth**

### 4️⃣ Migrations Base de Données

```bash
# Créer les migrations (si pas déjà fait)
python manage.py makemigrations

# Appliquer les migrations
python manage.py migrate

# Vérifier que les tables existent
python manage.py shell
>>> from cors.models import CloudStorageProvider, UserCloudStorage
>>> CloudStorageProvider.objects.all()
>>> exit()
```

### 5️⃣ Initialiser les Providers

```bash
# Exécuter le script d'initialisation
python scripts/init_cloud_providers.py

# Vérifier
python manage.py shell
>>> from cors.models import CloudStorageProvider
>>> CloudStorageProvider.objects.values_list('name', 'code', 'is_active')
# Devrait afficher : Google Drive, OneDrive, Dropbox, Local Storage
>>> exit()
```

### 6️⃣ Démarrer les Services

#### Terminal 1 : Django
```bash
python manage.py runserver
```

#### Terminal 2 : Celery Worker
```bash
celery -A doc worker -l info
```

#### Terminal 3 : Celery Beat (tâches périodiques)
```bash
celery -A doc beat -l info
```

---

## 🧪 Tests de Validation

### Test 1 : Vérifier les endpoints OAuth

```bash
# Lister les providers
curl http://localhost:8000/api/cloud-storage/providers/

# Devrait retourner Google Drive, OneDrive, Dropbox
```

### Test 2 : Initier un flow OAuth (requiert authentification)

```bash
# Obtenir un token user d'abord
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email": "votre@email.com", "password": "votrepassword"}'

# Utiliser le token pour initier OAuth
curl -X POST http://localhost:8000/api/cloud-storage/oauth/initiate/ \
  -H "Authorization: Bearer <votre-token>" \
  -H "Content-Type: application/json" \
  -d '{"provider_id": 1}'
```

### Test 3 : Tester Celery

```bash
# Dans un shell Python
python manage.py shell

>>> from cors.tasks import sync_quota_task
>>> result = sync_quota_task.delay()
>>> result.status
# Devrait être 'SUCCESS' après quelques secondes

>>> exit()
```

---

## 📊 Monitoring

### Vérifier les logs Celery

```bash
# Dans le terminal Celery worker
# Cherchez des messages comme :
[2026-04-01 14:50:00,000: INFO] Task cors.tasks.sync_quota_task[...] succeeded
```

### Vérifier les logs Django

```bash
# Dans le terminal Django runserver
# Cherchez des messages comme :
INFO - Google Drive backend registered
INFO - OneDrive backend registered
INFO - Dropbox backend registered
```

---

## 🔧 Dépannage

### Erreur : "No module named 'msal'"
```bash
pip install msal==1.31.1
```

### Erreur : "CLOUD_STORAGE_ENCRYPTION_KEY not set"
```bash
# Générer une clé
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# L'ajouter dans .env
echo "CLOUD_STORAGE_ENCRYPTION_KEY=<votre-clé>" >> .env
```

### Erreur : OAuth callback 404
Vérifiez que l'URL de callback dans votre app OAuth correspond exactement à :
- Google : `http://localhost:8000/api/cloud-storage/oauth/callback/google/`
- OneDrive : `http://localhost:8000/api/cloud-storage/oauth/callback/onedrive/`
- Dropbox : `http://localhost:8000/api/cloud-storage/oauth/callback/dropbox/`

### Celery ne démarre pas
```bash
# Vérifier que Redis tourne
redis-cli ping
# Devrait retourner "PONG"

# Si Redis n'est pas installé
sudo apt install redis-server   # Ubuntu/Debian
brew install redis               # macOS
redis-server                     # Démarrer Redis
```

---

## 📖 Documentation

| Document | Description |
|----------|-------------|
| `FINAL_DELIVERY_SUMMARY.md` | 📊 Récapitulatif complet du projet |
| `CLOUD_STORAGE_README.md` | 📘 Guide technique détaillé |
| `CLOUD_STORAGE_CONFIG.md` | ⚙️ Configuration OAuth providers |
| `PHASE_3_4_5_COMPLETED.md` | ✅ Détails phases 3-5 |
| `IMPLEMENTATION_SUMMARY.md` | 🏗️ Vue d'ensemble architecture |

---

## 🎯 Utilisation Rapide

### Connecter un compte Google Drive (via API)

```bash
# 1. Initier OAuth
curl -X POST http://localhost:8000/api/cloud-storage/oauth/initiate/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"provider_id": 1, "display_name": "Mon Google Drive"}'

# 2. Ouvrir l'URL retournée dans le navigateur
# 3. Autoriser l'application
# 4. Le callback enregistrera automatiquement la connexion
```

### Uploader un fichier vers le cloud (asynchrone)

```bash
curl -X POST http://localhost:8000/api/documents/files/move-to-cloud/123/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "target_storage_id": 1,
    "async": true
  }'

# Retourne un task_id pour suivre le progrès
```

---

## ✅ Checklist Finale

Avant de mettre en production :

- [ ] Tous les packages Python installés
- [ ] `.env` configuré avec clé de chiffrement
- [ ] Credentials OAuth créés (Google, OneDrive, Dropbox)
- [ ] Migrations appliquées
- [ ] Providers initialisés
- [ ] Redis démarré
- [ ] Celery worker démarré
- [ ] Celery beat démarré
- [ ] Tests OAuth réussis
- [ ] Upload test réussi
- [ ] Logs sans erreurs

---

## 🎉 Félicitations !

Si tous les tests passent, votre système cloud storage multi-provider est **opérationnel** ! 🚀

Pour toute question, consultez la documentation dans les fichiers `.md` ou les commentaires dans le code.

**Bon déploiement !** 👨‍💻
