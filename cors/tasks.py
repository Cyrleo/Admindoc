from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from cors.models import Reminder, ReminderLog


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
