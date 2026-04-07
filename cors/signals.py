from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from uuid import UUID

from cors.models import AuditLog, Category, Document, Reminder, SharedLink, Tag
from cors.request_context import get_current_user

TRACKED_MODELS = (Category, Tag, Document, Reminder, SharedLink)


def _get_actor():
    user = get_current_user()
    if user is not None and getattr(user, "is_authenticated", False):
        return user
    return None


def _build_meta(instance):
    def _json_safe(value):
        if isinstance(value, UUID):
            return str(value)
        return value

    meta = {}
    for field_name in ("name", "title", "token"):
        if hasattr(instance, field_name):
            value = getattr(instance, field_name)
            if value is not None:
                meta[field_name] = str(value)
    if hasattr(instance, "document_id"):
        meta["document_id"] = _json_safe(instance.document_id)
    if hasattr(instance, "creator_id"):
        meta["creator_id"] = _json_safe(instance.creator_id)
    if hasattr(instance, "owner_id"):
        meta["owner_id"] = _json_safe(instance.owner_id)
    return meta


def _log(action, instance):
    AuditLog.objects.create(
        user=_get_actor(),
        action=action,
        target_type=instance.__class__.__name__,
        target_id=str(instance.pk),
        meta=_build_meta(instance),
    )


@receiver(post_save)
def audit_post_save(sender, instance, created, **kwargs):
    if sender not in TRACKED_MODELS:
        return
    _log(f"{'created' if created else 'updated'}_{sender.__name__.lower()}", instance)


@receiver(post_delete)
def audit_post_delete(sender, instance, **kwargs):
    if sender not in TRACKED_MODELS:
        return
    _log(f"deleted_{sender.__name__.lower()}", instance)
