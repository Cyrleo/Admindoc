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
    """
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to="documents/%Y/%m/%d/")
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
