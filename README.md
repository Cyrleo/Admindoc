# AdminDoc Backend

Backend Django/DRF pour la gestion de documents administratifs.

## Fonctionnalités actuellement branchées

- Auth JWT avec Djoser et utilisateur custom email
- Social auth Google et GitHub
- CRUD documents, catégories, tags, rappels, liens de partage, audit logs
- Upload local de documents en dev
- Swagger / ReDoc
- Lien public de partage par token
- Stripe checkout + webhook (config via variables d'environnement)
- Celery + Redis pour les rappels asynchrones

## Structure du projet

- `requirements.txt` : dépendances Python
- `doc/` : projet Django (settings/urls/wsgi)
- `manage.py` : entrée Django
- `.env.example` : exemple des variables d'environnement
- `cors/pages/admin_api/` : API REST d'administration (RBAC)
- `scripts/` : scripts opérationnels (init rôles, checks, fix venv)

## RBAC admin (multi-rôles)

- Les rôles admin sont portés par les groupes Django.
- Un utilisateur peut avoir plusieurs rôles simultanément.
- Endpoint d'assignation multi-rôles : `POST /api/admin/v1/users/{id}/set-roles/`
- Endpoint matrice rôles/capacités : `GET /api/admin/v1/system/roles/`

Initialiser les groupes de rôles :

```bash
python scripts/init_admin_roles.py
```

## Prérequis

- Python 3.10+
- PostgreSQL
- Redis
- Un provider SMTP si tu veux les emails réels

## 1. Cloner et préparer l'environnement Python

Depuis la racine du repo :

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Configurer la base PostgreSQL

Le projet utilise PostgreSQL par défaut.

Exemple de création de base et utilisateur local :

```bash
sudo -u postgres psql
```

Puis dans `psql` :

```sql
CREATE DATABASE docs;
CREATE USER postgres WITH PASSWORD 'azertyuiop';
GRANT ALL PRIVILEGES ON DATABASE docs TO postgres;
```

Si ton user `postgres` existe déjà, garde seulement la base et vérifie le mot de passe.

## 3. Configurer les variables d'environnement

Le projet lit les variables directement depuis l'environnement. Tu peux t'appuyer sur [doc/.env.example](doc/.env.example).

Variables DB minimales :

```env
DB_NAME=docs
DB_USER=postgres
DB_PASSWORD=azertyuiop
DB_HOST=localhost
DB_PORT=5432
```

Exemple d'export manuel en shell :

```bash
export DB_NAME=docs
export DB_USER=postgres
export DB_PASSWORD=azertyuiop
export DB_HOST=localhost
export DB_PORT=5432
```

## 4. Configurer l'email SMTP

Le backend utilise un provider SMTP réel par défaut.

Exemple Brevo / SMTP classique :

```env
DEFAULT_FROM_EMAIL=no-reply@ton-domaine.com
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp-relay.brevo.com
EMAIL_PORT=587
EMAIL_HOST_USER=ton-login-smtp
EMAIL_HOST_PASSWORD=ton-mot-de-passe-smtp
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
EMAIL_TIMEOUT=30
```

Tu peux adapter cette configuration pour Brevo, SendGrid SMTP, Mailgun SMTP ou tout autre fournisseur SMTP.

## 5. Configurer Redis / Celery

Redis est utilisé comme broker et backend Celery pour les tâches asynchrones.

Variables par défaut :

```env
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

Lancer Redis localement si nécessaire :

```bash
redis-server
```

Ou vérifier qu'il tourne déjà :

```bash
redis-cli ping
```

## 6. Configurer Stripe

Pour activer le checkout et les webhooks Stripe :

```env
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
```

Sans ces clés, les endpoints Stripe existent mais répondront que Stripe n'est pas configuré.

## 7. Configurer Google / GitHub social auth

```env
SOCIAL_AUTH_GOOGLE_OAUTH2_KEY=
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET=
SOCIAL_AUTH_GITHUB_KEY=
SOCIAL_AUTH_GITHUB_SECRET=
DJOSER_SOCIAL_AUTH_ALLOWED_REDIRECT_URIS=http://localhost:3000/auth/callback
```

## 8. Appliquer les migrations

Depuis la racine du repo :

```bash
python manage.py migrate
```

Si tu veux initialiser les catégories et tags par défaut :

```bash
python scripts/init_db_defaults.py
```

Ou sans relancer les migrations :

```bash
python scripts/init_db_defaults.py --skip-migrate
```

## 9. Démarrer le serveur Django

Depuis la racine du repo :

```bash
python manage.py runserver
```

Accès local :

- Swagger : http://127.0.0.1:8000/api/docs/
- ReDoc : http://127.0.0.1:8000/api/redoc/
- Admin Django : http://127.0.0.1:8000/admin/

## 10. Démarrer les workers asynchrones

Dans des terminaux séparés, depuis la racine du repo :

Worker Celery :

```bash
celery -A doc worker -l info
```

Scheduler Celery Beat :

```bash
celery -A doc beat -l info
```

Si `celery` n'est pas trouvé dans le shell :

```bash
venv/bin/celery -A doc worker -l info
venv/bin/celery -A doc beat -l info
```

## 11. Commandes utiles

Créer un superuser :

```bash
python manage.py createsuperuser
```

Vérifier la config Django :

```bash
python manage.py check
```

Générer des migrations après changement de modèles :

```bash
python manage.py makemigrations
python manage.py migrate
```

## 12. Ordre de démarrage recommandé en local

1. Démarrer PostgreSQL
2. Démarrer Redis
3. Activer le virtualenv
4. Exporter les variables d'environnement
5. Lancer `python manage.py migrate`
6. Lancer `python manage.py runserver`
7. Lancer `celery -A doc worker -l info`
8. Lancer `celery -A doc beat -l info`

## Variables d'environnement principales

- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`
- `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
- `DEFAULT_FROM_EMAIL`, `EMAIL_BACKEND`
- `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`
- `EMAIL_USE_TLS`, `EMAIL_USE_SSL`, `EMAIL_TIMEOUT`
- `SOCIAL_AUTH_GOOGLE_OAUTH2_KEY`, `SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET`
- `SOCIAL_AUTH_GITHUB_KEY`, `SOCIAL_AUTH_GITHUB_SECRET`
- `DJOSER_SOCIAL_AUTH_ALLOWED_REDIRECT_URIS`

## 13. Déploiement production (Linux)

### Préparer les variables

Copie `.env.example` puis adapte les valeurs de production :

```bash
cp .env.example .env
```

Variables critiques pour démarrer en production :

- `DJANGO_SECRET_KEY`
- `DEBUG=false`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `DATABASE_URL` (ou variables `DB_*`)
- `CELERY_BROKER_URL`

### Installer les dépendances et préparer Django

```bash
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check --deploy
```

### Vérification pré-déploiement recommandée

```bash
./scripts/predeploy_check.sh
```

### Démarrer l'API (Gunicorn)

```bash
gunicorn doc.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120
```

### Démarrer Celery en production

Dans 2 services/process séparés :

```bash
celery -A doc worker -l info
celery -A doc beat -l info
```

### Reverse proxy recommandé

Mettez Nginx (ou équivalent) devant Gunicorn avec HTTPS, puis transmettez
`X-Forwarded-Proto` pour que Django applique correctement les redirections SSL.
