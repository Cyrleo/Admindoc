from django.db import models
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone
import uuid


class Category(models.Model):
    """
    Category for a user's documents (e.g. 'Factures', 'Contrats', ...).
    - is_default=True, owner=None  → shared, visible to all without auth (read-only for non-staff)
    - is_default=False, owner=User → personal category, visible only to its owner
    """
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="categories",
    )
    name = models.CharField(max_length=150)
    color = models.CharField(max_length=7, blank=True, help_text="Hex color like #RRGGBB")
    icon = models.CharField(max_length=64, blank=True, help_text="Optional icon name")
    is_default = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Si True, catégorie partagée accessible sans authentification",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "name"],
                condition=models.Q(owner__isnull=False),
                name="unique_category_per_owner",
            ),
            models.UniqueConstraint(
                fields=["name"],
                condition=models.Q(is_default=True),
                name="unique_default_category_name",
            ),
        ]

    def __str__(self):
        return self.name


class Tag(models.Model):
    """
    Simple tag model to attach arbitrary tags to documents.
    - is_default=True, owner=None  -> shared, visible to all without auth
    - is_default=False, owner=User -> personal tag scoped to owner
    """
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="tags",
    )
    name = models.CharField(max_length=64)
    is_default = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Si True, tag partagé accessible sans authentification",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "name"],
                condition=models.Q(owner__isnull=False),
                name="unique_tag_per_owner",
            ),
            models.UniqueConstraint(
                fields=["name"],
                condition=models.Q(is_default=True),
                name="unique_default_tag_name",
            ),
        ]

    def __str__(self):
        return self.name


class Document(models.Model):
    """
    Core Document model storing metadata and a pointer to the uploaded file.
    In this simple dev setup we use Django's default FileField (local MEDIA_ROOT).
    
    Note: The 'file' field is deprecated. Use DocumentFile model instead for multi-file support.
    """
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    # DEPRECATED: Use DocumentFile model instead
    file = models.FileField(upload_to="documents/%Y/%m/%d/", null=True, blank=True)
    file_name = models.CharField(max_length=512, blank=True)
    mime_type = models.CharField(max_length=100, blank=True)
    size = models.PositiveBigIntegerField(null=True, blank=True, help_text="File size in bytes")
    category = models.ForeignKey(
        Category,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="documents",
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name="documents")
    date_issued = models.DateField(null=True, blank=True)
    date_expiration = models.DateField(null=True, blank=True)
    is_encrypted = models.BooleanField(default=False)
    checksum = models.CharField(max_length=128, blank=True, help_text="Optional file checksum")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    archived = models.BooleanField(default=False)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.title} ({self.owner})"


class DocumentFile(models.Model):
    """
    Individual file attached to a Document.
    Allows multiple files per document (e.g., multiple scans, PDFs, images for one birth certificate).
    Can be stored locally or on cloud storage.
    """
    STORAGE_LOCAL = 'local'
    STORAGE_CLOUD = 'cloud'
    STORAGE_CHOICES = [
        (STORAGE_LOCAL, 'Local'),
        (STORAGE_CLOUD, 'Cloud'),
    ]
    
    SYNC_PENDING = 'pending'
    SYNC_UPLOADING = 'uploading'
    SYNC_SYNCED = 'synced'
    SYNC_ERROR = 'error'
    SYNC_STATUS_CHOICES = [
        (SYNC_PENDING, 'En attente'),
        (SYNC_UPLOADING, 'Upload en cours'),
        (SYNC_SYNCED, 'Synchronisé'),
        (SYNC_ERROR, 'Erreur'),
    ]
    
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="files",
    )
    
    # Fichier local (peut être vide si stocké uniquement dans le cloud)
    file = models.FileField(upload_to="document_files/%Y/%m/%d/", blank=True)
    file_name = models.CharField(max_length=512, help_text="Original filename")
    mime_type = models.CharField(max_length=100, blank=True)
    size = models.PositiveBigIntegerField(help_text="File size in bytes")
    is_primary = models.BooleanField(
        default=False,
        help_text="Primary/main file for this document"
    )
    
    # Stockage cloud
    storage_type = models.CharField(
        max_length=20,
        choices=STORAGE_CHOICES,
        default=STORAGE_LOCAL,
        help_text="Type de stockage (local ou cloud)"
    )
    cloud_storage = models.ForeignKey(
        'UserCloudStorage',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='files',
        help_text="Connexion cloud où le fichier est stocké"
    )
    cloud_file_id = models.CharField(
        max_length=512,
        blank=True,
        help_text="ID du fichier chez le provider cloud"
    )
    cloud_file_path = models.CharField(
        max_length=1024,
        blank=True,
        help_text="Chemin complet dans le cloud"
    )
    cloud_url = models.CharField(
        max_length=2048,
        blank=True,
        help_text="URL de partage/preview du fichier cloud"
    )
    cloud_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Métadonnées du provider cloud"
    )
    
    # État de synchronisation
    sync_status = models.CharField(
        max_length=20,
        choices=SYNC_STATUS_CHOICES,
        default=SYNC_PENDING
    )
    sync_error = models.TextField(blank=True)
    last_synced = models.DateTimeField(null=True, blank=True)
    
    uploaded_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-is_primary", "-uploaded_at")

    def __str__(self):
        storage_info = f"[{self.get_storage_type_display()}]"
        return f"{storage_info} {self.file_name} ({self.document.title})"


class Reminder(models.Model):
    """
    Reminder configuration for a document expiration.
    A periodic job should create/send reminders according to `days_before`.
    """
    METHOD_EMAIL = "email"
    METHOD_PUSH = "push"
    METHOD_CHOICES = [
        (METHOD_EMAIL, "Email"),
        (METHOD_PUSH, "Push Notification"),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reminders",
    )
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="reminders",
    )
    days_before = models.PositiveIntegerField(help_text="Days before expiration to notify (e.g. 7)")
    method = models.CharField(max_length=10, choices=METHOD_CHOICES, default=METHOD_EMAIL)
    enabled = models.BooleanField(default=True)
    next_run = models.DateTimeField(null=True, blank=True)
    last_sent = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("next_run",)

    def schedule_next_run(self):
        """
        Compute and set `next_run` based on the document's `date_expiration`
        and this reminder's `days_before`. Returns the computed datetime or None.
        """
        if not self.document.date_expiration:
            return None
        target_date = timezone.make_aware(
            timezone.datetime.combine(self.document.date_expiration, timezone.datetime.min.time())
        )
        run_dt = target_date - timezone.timedelta(days=self.days_before)
        self.next_run = run_dt
        self.save(update_fields=["next_run"])
        return self.next_run

    def __str__(self):
        return f"Reminder: {self.document} - {self.days_before}d before"


class ReminderLog(models.Model):
    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SENT, "Sent"),
        (STATUS_FAILED, "Failed"),
    ]

    recipient = models.EmailField()
    reminder = models.ForeignKey(
        Reminder,
        on_delete=models.CASCADE,
        related_name="logs",
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    sent_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"ReminderLog({self.recipient}, {self.status})"


class SharedLink(models.Model):
    """
    Secure temporary share link for a document.
    Uses a UUID token to reference the link. Optionally protected by password,
    with download limits and expiration.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="shared_links",
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_shared_links",
    )
    token = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    password_required = models.BooleanField(default=False)
    password_hash = models.CharField(max_length=128, blank=True)  # store hashed password if used
    expires_at = models.DateTimeField(null=True, blank=True)
    max_downloads = models.PositiveIntegerField(null=True, blank=True, help_text="Null = unlimited")
    download_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        if not self.is_active:
            return True
        if self.expires_at and timezone.now() >= self.expires_at:
            return True
        if self.max_downloads is not None and self.download_count >= self.max_downloads:
            return True
        return False

    def set_password(self, raw_password):
        if raw_password:
            self.password_required = True
            self.password_hash = make_password(raw_password)
        else:
            self.password_required = False
            self.password_hash = ""

    def check_password(self, raw_password):
        if not self.password_required:
            return True
        if not raw_password or not self.password_hash:
            return False
        return check_password(raw_password, self.password_hash)

    def increment_download(self):
        type(self).objects.filter(pk=self.pk).update(
            download_count=models.F("download_count") + 1
        )
        self.refresh_from_db(fields=["download_count"])

    def __str__(self):
        return f"SharedLink {self.token} -> {self.document}"


class AuditLog(models.Model):
    """
    Lightweight audit log for important user actions.
    Store free-form metadata in JSON for flexibility.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=128)
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.CharField(max_length=128, blank=True)
    meta = models.JSONField(blank=True, default=dict)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-timestamp",)

    def __str__(self):
        return f"{self.timestamp.isoformat()} - {self.user} - {self.action}"


class Subscription(models.Model):
    PLAN_FREE = "free"
    PLAN_PRO = "pro"
    PLAN_BUSINESS = "business"
    PLAN_CHOICES = [
        (PLAN_FREE, "Free"),
        (PLAN_PRO, "Pro"),
        (PLAN_BUSINESS, "Business"),
    ]

    STATUS_INCOMPLETE = "incomplete"
    STATUS_ACTIVE = "active"
    STATUS_PAST_DUE = "past_due"
    STATUS_CANCELED = "canceled"
    STATUS_UNPAID = "unpaid"
    STATUS_TRIALING = "trialing"
    STATUS_CHOICES = [
        (STATUS_INCOMPLETE, "Incomplete"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_PAST_DUE, "Past due"),
        (STATUS_CANCELED, "Canceled"),
        (STATUS_UNPAID, "Unpaid"),
        (STATUS_TRIALING, "Trialing"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscription",
    )
    stripe_customer_id = models.CharField(max_length=255, blank=True)
    stripe_subscription_id = models.CharField(max_length=255, blank=True)
    plan = models.CharField(max_length=32, choices=PLAN_CHOICES, default=PLAN_FREE)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_INCOMPLETE)
    current_period_end = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)

    def __str__(self):
        return f"Subscription({self.user}, {self.plan}, {self.status})"


class CloudStorageProvider(models.Model):
    """
    Définition des providers de stockage cloud supportés.
    """
    PROVIDER_GOOGLE_DRIVE = 'google_drive'
    PROVIDER_ONEDRIVE = 'onedrive'
    PROVIDER_DROPBOX = 'dropbox'
    PROVIDER_TERRABOX = 'terrabox'
    PROVIDER_LOCAL = 'local'
    PROVIDER_AWS_S3 = 'aws_s3'
    PROVIDER_AZURE_BLOB = 'azure_blob'
    
    PROVIDER_CHOICES = [
        (PROVIDER_GOOGLE_DRIVE, 'Google Drive'),
        (PROVIDER_ONEDRIVE, 'Microsoft OneDrive'),
        (PROVIDER_DROPBOX, 'Dropbox'),
        (PROVIDER_TERRABOX, 'Terrabox'),
        (PROVIDER_LOCAL, 'Serveur Local'),
        (PROVIDER_AWS_S3, 'Amazon S3'),
        (PROVIDER_AZURE_BLOB, 'Azure Blob Storage'),
    ]
    
    code = models.CharField(max_length=50, unique=True, choices=PROVIDER_CHOICES)
    name = models.CharField(max_length=100)
    icon = models.CharField(max_length=255, blank=True, help_text="URL ou nom d'icône")
    is_active = models.BooleanField(default=True)
    requires_oauth = models.BooleanField(default=True)
    api_base_url = models.CharField(max_length=255, blank=True)
    oauth_authorize_url = models.CharField(max_length=255, blank=True)
    oauth_token_url = models.CharField(max_length=255, blank=True)
    scopes = models.JSONField(default=list, help_text="Scopes OAuth requis")
    config = models.JSONField(default=dict, help_text="Configuration spécifique au provider")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ("name",)
    
    def __str__(self):
        return self.name


class UserCloudStorage(models.Model):
    """
    Connexion d'un utilisateur à un provider de stockage cloud.
    Les tokens OAuth sont stockés de manière chiffrée.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='cloud_storages'
    )
    provider = models.ForeignKey(
        CloudStorageProvider,
        on_delete=models.PROTECT,
        related_name='user_connections'
    )
    
    # Authentification OAuth (chiffrés)
    _access_token = models.CharField(max_length=512, db_column='access_token')
    _refresh_token = models.CharField(max_length=512, blank=True, db_column='refresh_token')
    token_expires_at = models.DateTimeField(null=True, blank=True)
    
    # Informations du compte cloud
    cloud_account_id = models.CharField(max_length=255)
    cloud_account_email = models.EmailField(blank=True)
    cloud_account_name = models.CharField(max_length=255, blank=True)
    
    # Configuration
    display_name = models.CharField(max_length=100, help_text="Nom personnalisé par l'utilisateur")
    is_default = models.BooleanField(default=False, help_text="Stockage par défaut pour ce user?")
    is_active = models.BooleanField(default=True)
    
    # Quotas et limites (si disponibles via API)
    total_space = models.BigIntegerField(null=True, blank=True, help_text="Espace total en bytes")
    used_space = models.BigIntegerField(null=True, blank=True, help_text="Espace utilisé en bytes")
    last_sync = models.DateTimeField(null=True, blank=True)
    
    # Paramètres avancés
    base_folder = models.CharField(max_length=500, default='AdminDoc/', help_text="Dossier racine")
    auto_organize = models.BooleanField(default=True, help_text="Organiser par catégories?")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['user', 'provider', 'cloud_account_id']
        ordering = ['-is_default', 'display_name']
    
    def __str__(self):
        return f"{self.display_name} ({self.provider.name}) - {self.user.email}"
    
    @property
    def access_token(self):
        """Déchiffre et retourne le token d'accès."""
        from cors.utils.encryption import TokenEncryption
        encryptor = TokenEncryption()
        return encryptor.decrypt(self._access_token)
    
    @access_token.setter
    def access_token(self, value):
        """Chiffre et stocke le token d'accès."""
        from cors.utils.encryption import TokenEncryption
        encryptor = TokenEncryption()
        self._access_token = encryptor.encrypt(value)
    
    @property
    def refresh_token(self):
        """Déchiffre et retourne le refresh token."""
        if not self._refresh_token:
            return ''
        from cors.utils.encryption import TokenEncryption
        encryptor = TokenEncryption()
        return encryptor.decrypt(self._refresh_token)
    
    @refresh_token.setter
    def refresh_token(self, value):
        """Chiffre et stocke le refresh token."""
        if not value:
            self._refresh_token = ''
            return
        from cors.utils.encryption import TokenEncryption
        encryptor = TokenEncryption()
        self._refresh_token = encryptor.encrypt(value)
    
    @property
    def available_space(self):
        """Calcule l'espace disponible en bytes."""
        if self.total_space is None or self.used_space is None:
            return None
        return self.total_space - self.used_space



class CloudStorageActivity(models.Model):
    """
    Historique des activités sur le stockage cloud.
    """
    ACTION_CONNECT = 'connect'
    ACTION_DISCONNECT = 'disconnect'
    ACTION_UPLOAD = 'upload'
    ACTION_DOWNLOAD = 'download'
    ACTION_DELETE = 'delete'
    ACTION_SYNC = 'sync'
    ACTION_ERROR = 'error'
    
    ACTION_CHOICES = [
        (ACTION_CONNECT, 'Connexion'),
        (ACTION_DISCONNECT, 'Déconnexion'),
        (ACTION_UPLOAD, 'Upload'),
        (ACTION_DOWNLOAD, 'Download'),
        (ACTION_DELETE, 'Suppression'),
        (ACTION_SYNC, 'Synchronisation'),
        (ACTION_ERROR, 'Erreur'),
    ]
    
    user_storage = models.ForeignKey(
        UserCloudStorage,
        on_delete=models.CASCADE,
        related_name='activities'
    )
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    document_file = models.ForeignKey(
        DocumentFile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='cloud_activities'
    )
    details = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ('-timestamp',)
        verbose_name_plural = 'Cloud Storage Activities'
    
    def __str__(self):
        return f"{self.get_action_display()} - {self.user_storage} - {self.timestamp}"

