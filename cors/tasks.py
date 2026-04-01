from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.core.files.base import ContentFile

from cors.models import Reminder, ReminderLog, UserCloudStorage, DocumentFile, CloudStorageActivity
from cors.storage.factory import CloudStorageFactory
from cors.storage.token_manager import TokenManager
import logging

logger = logging.getLogger(__name__)


def enqueue_reminder_email(reminder_id):
    delay = getattr(send_reminder_email_task, "delay", None)
    if callable(delay):
        return delay(reminder_id)
    return send_reminder_email_task(reminder_id)


@shared_task
def send_reminder_email_task(reminder_id):
    try:
        reminder = Reminder.objects.select_related("owner", "document").get(pk=reminder_id)
    except Reminder.DoesNotExist:
        return {"status": "missing", "reminder_id": reminder_id}

    recipient = reminder.owner.email
    log = ReminderLog.objects.create(recipient=recipient, reminder=reminder)

    if not recipient:
        log.status = ReminderLog.STATUS_FAILED
        log.error_message = "Recipient email is missing."
        log.save(update_fields=["status", "error_message"])
        return {"status": "failed", "reason": "missing email"}

    subject = f"Rappel: {reminder.document.title} expire bientot"
    expiration = reminder.document.date_expiration.isoformat() if reminder.document.date_expiration else "date inconnue"
    message = (
        f"Bonjour,\n\n"
        f"Le document '{reminder.document.title}' arrive a expiration le {expiration}.\n"
        f"Rappel configure a {reminder.days_before} jour(s) avant expiration.\n"
    )

    try:
        send_mail(
            subject,
            message,
            getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@admindoc.local"),
            [recipient],
            fail_silently=False,
        )
    except Exception as exc:
        log.status = ReminderLog.STATUS_FAILED
        log.error_message = str(exc)
        log.save(update_fields=["status", "error_message"])
        return {"status": "failed", "reason": str(exc)}

    now = timezone.now()
    reminder.last_sent = now
    reminder.save(update_fields=["last_sent"])

    log.status = ReminderLog.STATUS_SENT
    log.sent_at = now
    log.save(update_fields=["status", "sent_at"])
    return {"status": "sent", "reminder_id": reminder_id}


@shared_task
def schedule_due_reminders_task():
    now = timezone.now()
    due_reminders = Reminder.objects.filter(enabled=True, next_run__isnull=False, next_run__lte=now)
    reminder_ids = list(due_reminders.values_list("id", flat=True))
    for reminder_id in reminder_ids:
        enqueue_reminder_email(reminder_id)
    return {"scheduled": reminder_ids}


# ==================== Cloud Storage Tasks ====================

@shared_task(bind=True, max_retries=3)
def upload_file_to_cloud_task(self, document_file_id, user_storage_id, folder_path=''):
    """
    Tâche Celery pour uploader un fichier vers un stockage cloud de manière asynchrone.
    
    Args:
        document_file_id: ID du DocumentFile à uploader
        user_storage_id: ID du UserCloudStorage cible
        folder_path: Chemin du dossier cloud (optionnel)
        
    Returns:
        Dict avec status, file_id, cloud_url
    """
    try:
        # Récupérer les objets
        document_file = DocumentFile.objects.select_related('document', 'document__owner').get(id=document_file_id)
        user_storage = UserCloudStorage.objects.select_related('provider').get(id=user_storage_id)
        
        logger.info(f"Starting cloud upload: {document_file.nom_fichier} to {user_storage.provider.name}")
        
        # Vérifier que le token est valide
        TokenManager.ensure_valid_token(user_storage)
        
        # Obtenir le backend approprié
        backend = CloudStorageFactory.get_backend(user_storage)
        
        # Lire le fichier local
        if not document_file.fichier:
            raise ValueError(f"Document file {document_file_id} has no file attached")
        
        document_file.fichier.open('rb')
        file_content = document_file.fichier.read()
        document_file.fichier.close()
        
        # Upload vers le cloud
        result = backend.upload_file(
            file=ContentFile(file_content),
            path=folder_path,
            metadata={
                'name': document_file.nom_fichier,
                'mime_type': document_file.type_fichier,
            }
        )
        
        # Mettre à jour le DocumentFile
        document_file.storage_type = 'cloud'
        document_file.cloud_storage = user_storage
        document_file.cloud_file_id = result['file_id']
        document_file.cloud_url = result.get('url', '')
        document_file.save()
        
        # Logger l'activité
        CloudStorageActivity.objects.create(
            user_storage=user_storage,
            action='upload',
            file_name=document_file.nom_fichier,
            file_size=result.get('size', 0),
            details=f"Uploaded {document_file.nom_fichier} to {user_storage.provider.name}"
        )
        
        logger.info(f"Cloud upload completed: {document_file.nom_fichier} (ID: {result['file_id']})")
        
        return {
            'status': 'success',
            'document_file_id': document_file_id,
            'cloud_file_id': result['file_id'],
            'cloud_url': result.get('url', ''),
            'size': result.get('size', 0),
        }
        
    except DocumentFile.DoesNotExist:
        logger.error(f"DocumentFile {document_file_id} not found")
        return {'status': 'error', 'message': f'DocumentFile {document_file_id} not found'}
        
    except UserCloudStorage.DoesNotExist:
        logger.error(f"UserCloudStorage {user_storage_id} not found")
        return {'status': 'error', 'message': f'UserCloudStorage {user_storage_id} not found'}
        
    except Exception as exc:
        logger.error(f"Cloud upload failed for {document_file_id}: {exc}", exc_info=True)
        
        # Retry si pas encore atteint le max
        try:
            raise self.retry(exc=exc, countdown=60)  # Retry après 60 secondes
        except self.MaxRetriesExceededError:
            return {
                'status': 'error',
                'message': str(exc),
                'max_retries_exceeded': True
            }


@shared_task
def sync_quota_task(user_storage_id=None):
    """
    Tâche Celery pour synchroniser les quotas de stockage cloud.
    
    Args:
        user_storage_id: ID spécifique à synchroniser, ou None pour tous
        
    Returns:
        Dict avec nombre de quotas synchronisés
    """
    try:
        if user_storage_id:
            storages = UserCloudStorage.objects.filter(id=user_storage_id, is_active=True)
        else:
            storages = UserCloudStorage.objects.filter(is_active=True)
        
        synced_count = 0
        errors = []
        
        for user_storage in storages.select_related('provider'):
            try:
                # Vérifier le token
                TokenManager.ensure_valid_token(user_storage)
                
                # Obtenir le backend
                backend = CloudStorageFactory.get_backend(user_storage)
                
                # Récupérer les infos de quota
                quota_info = backend.get_quota_info()
                
                # Mettre à jour
                user_storage.storage_quota_total = quota_info.get('total_space', 0)
                user_storage.storage_quota_used = quota_info.get('used_space', 0)
                user_storage.last_synced_at = timezone.now()
                user_storage.save(update_fields=['storage_quota_total', 'storage_quota_used', 'last_synced_at'])
                
                synced_count += 1
                logger.debug(f"Quota synced for {user_storage.provider.name}: {user_storage.storage_quota_used}/{user_storage.storage_quota_total}")
                
            except Exception as e:
                error_msg = f"Failed to sync quota for UserCloudStorage {user_storage.id}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        return {
            'status': 'success',
            'synced': synced_count,
            'errors': errors
        }
        
    except Exception as exc:
        logger.error(f"Quota sync task failed: {exc}", exc_info=True)
        return {
            'status': 'error',
            'message': str(exc)
        }


@shared_task
def cleanup_orphaned_cloud_files_task():
    """
    Tâche Celery pour nettoyer les fichiers cloud orphelins.
    Supprime les fichiers cloud qui ne sont plus référencés dans la DB.
    
    Returns:
        Dict avec nombre de fichiers nettoyés
    """
    try:
        # Cette tâche nécessiterait de lister tous les fichiers cloud
        # et de vérifier s'ils existent dans DocumentFile
        # Pour l'instant, on retourne juste un placeholder
        
        logger.info("Cleanup orphaned cloud files task started (not implemented)")
        
        return {
            'status': 'success',
            'cleaned': 0,
            'message': 'Cleanup not implemented yet'
        }
        
    except Exception as exc:
        logger.error(f"Cleanup task failed: {exc}", exc_info=True)
        return {
            'status': 'error',
            'message': str(exc)
        }
