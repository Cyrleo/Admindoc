"""Vues de l'API d'administration.

Objectifs principaux:
- centraliser les operations back-office
- appliquer un controle d'acces par roles
- tracer les actions sensibles (audit)
- proteger les endpoints avec throttling
"""

import csv
from datetime import timedelta
from django.conf import settings
from django.core.cache import cache
from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response
from rest_framework.exceptions import Throttled
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from django.contrib.auth.models import Group

from accounts.models import User
from cors.models import (
    AuditLog,
    Category,
    CloudStorageActivity,
    CloudStorageProvider,
    Document,
    DocumentFile,
    Reminder,
    ReminderLog,
    Subscription,
    Tag,
    UserCloudStorage,
)
from cors.pages.admin_api.permissions import (
    ADMIN_ROLE_CAPABILITIES,
    ADMIN_ROLE_NAMES,
    IsAuditAdmin,
    IsBillingAdmin,
    IsCloudAdmin,
    IsDashboardAdmin,
    IsDocumentAdmin,
    IsDocumentReadAdmin,
    IsReminderAdmin,
    IsSystemAdmin,
    IsTaxonomyAdmin,
    IsUserAdmin,
    IsUserPrivilegeAdmin,
)
from cors.pages.admin_api.serializers import (
    AdminAuditLogSerializer,
    AdminCloudActivitySerializer,
    AdminCloudConnectionSerializer,
    AdminCloudStorageProviderSerializer,
    AdminDefaultCategorySerializer,
    AdminDefaultTagSerializer,
    AdminDocumentFileSerializer,
    AdminDocumentSerializer,
    AdminReminderLogSerializer,
    AdminReminderSerializer,
    AdminSubscriptionSerializer,
    AdminUserSerializer,
)
from cors.tasks import enqueue_reminder_email, export_audit_logs_task, schedule_due_reminders_task


def _parse_bool(value, default=False):
    """Convertit proprement une valeur en booleen."""
    if value is None:
        return default
    return str(value).lower() in {"1", "true", "yes", "on"}


def _audit_admin_action(request, action, target_type, target_id, meta=None):
    """Enregistre une action d'administration avec contexte requete."""
    request_meta = {
        "ip": request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", "")),
        "user_agent": request.META.get("HTTP_USER_AGENT", ""),
        "request_id": request.META.get("HTTP_X_REQUEST_ID", ""),
        "method": request.method,
        "path": request.path,
    }
    payload = dict(meta or {})
    payload.update({"request": request_meta})

    AuditLog.objects.create(
        user=request.user,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        meta=payload,
    )


def _enforce_local_rate_limit(request, scope, rate_key):
    """Applique un quota simple pour les vues sensibles.

    Ce fallback sert surtout pour les endpoints critiques quand on veut un
    comportement de test très deterministe.
    """
    rates = getattr(settings, "REST_FRAMEWORK", {}).get("DEFAULT_THROTTLE_RATES", {})
    rate = rates.get(rate_key)
    if not rate:
        return

    try:
        amount_text, period_text = rate.split("/", 1)
        amount = int(amount_text)
    except (ValueError, TypeError):
        return

    period_seconds = {
        "s": 1,
        "sec": 1,
        "second": 1,
        "seconds": 1,
        "m": 60,
        "min": 60,
        "minute": 60,
        "minutes": 60,
        "h": 3600,
        "hour": 3600,
        "hours": 3600,
        "d": 86400,
        "day": 86400,
        "days": 86400,
    }.get(period_text.lower(), 60)

    user_key = getattr(getattr(request, "user", None), "pk", None)
    ident = f"user:{user_key}" if user_key else f"ip:{request.META.get('REMOTE_ADDR', 'anonymous')}"
    cache_key = f"admin-rate:{scope}:{ident}"

    current = cache.get(cache_key)
    if current is None:
        cache.set(cache_key, 1, timeout=period_seconds)
        return

    if current >= amount:
        raise Throttled(detail="Limite de requetes atteinte pour cette operation.")

    cache.incr(cache_key)


class AdminThrottledAPIView(APIView):
    """Base APIView avec throttling scope admin par defaut."""
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "admin_default"


class AdminThrottledViewSet(viewsets.GenericViewSet):
    """Base ViewSet avec throttling scope admin par defaut."""
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "admin_default"


class AdminDashboardOverviewView(AdminThrottledAPIView):
    """Vue d'ensemble des indicateurs principaux de la plateforme."""
    permission_classes = [IsDashboardAdmin]
    throttle_scope = "admin_default"

    def get(self, request):
        now = timezone.now()
        last_30d = now - timedelta(days=30)

        data = {
            "users": {
                "total": User.objects.count(),
                "active": User.objects.filter(is_active=True).count(),
                "new_last_30d": User.objects.filter(date_joined__gte=last_30d).count(),
                "staff": User.objects.filter(is_staff=True).count(),
            },
            "documents": {
                "total": Document.objects.count(),
                "archived": Document.objects.filter(archived=True).count(),
                "expiring_30d": Document.objects.filter(
                    date_expiration__isnull=False,
                    date_expiration__lte=(now.date() + timedelta(days=30)),
                    date_expiration__gte=now.date(),
                ).count(),
            },
            "billing": {
                "active_subscriptions": Subscription.objects.filter(status=Subscription.STATUS_ACTIVE).count(),
                "past_due": Subscription.objects.filter(status=Subscription.STATUS_PAST_DUE).count(),
            },
            "cloud": {
                "providers_active": CloudStorageProvider.objects.filter(is_active=True).count(),
                "connections_active": UserCloudStorage.objects.filter(is_active=True).count(),
            },
        }
        return Response(data)


class AdminDashboardKpisView(AdminThrottledAPIView):
    """KPIs metier consolides pour pilotage admin."""
    permission_classes = [IsDashboardAdmin]
    throttle_scope = "admin_default"

    def get(self, request):
        docs_by_month = (
            Document.objects.annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(total=Count("id"))
            .order_by("month")
        )

        data = {
            "top_actions": list(
                AuditLog.objects.values("action").annotate(total=Count("id")).order_by("-total")[:10]
            ),
            "docs_by_month": list(docs_by_month),
            "subscriptions_by_plan": list(
                Subscription.objects.values("plan").annotate(total=Count("id")).order_by("plan")
            ),
        }
        return Response(data)


class AdminDashboardHealthView(AdminThrottledAPIView):
    """Etat de sante technique des integrations critiques."""
    permission_classes = [IsDashboardAdmin]
    throttle_scope = "admin_default"

    def get(self, request):
        payload = {
            "status": "ok",
            "time": timezone.now(),
            "checks": {
                "database": "ok",
                "celery_broker_configured": bool(getattr(settings, "CELERY_BROKER_URL", "")),
                "stripe_configured": bool(getattr(settings, "STRIPE_SECRET_KEY", "")),
                "email_configured": bool(getattr(settings, "EMAIL_HOST", "")),
            },
        }
        return Response(payload)


class AdminDashboardActivityFeedView(AdminThrottledAPIView):
    """Flux recent d'activite d'audit."""
    permission_classes = [IsDashboardAdmin]
    throttle_scope = "admin_default"

    def get(self, request):
        logs = AuditLog.objects.select_related("user").order_by("-timestamp")[:50]
        return Response(AdminAuditLogSerializer(logs, many=True).data)


class AdminUserViewSet(AdminThrottledViewSet, viewsets.ModelViewSet):
    """Gestion admin des utilisateurs.

Permet aussi d'assigner plusieurs roles admin via les groupes Django.
    """
    permission_classes = [IsUserAdmin]
    serializer_class = AdminUserSerializer
    queryset = User.objects.all().order_by("-date_joined")
    http_method_names = ["get", "post", "patch", "head", "options"]
    search_fields = ["email", "first_name", "last_name"]
    ordering_fields = ["date_joined", "last_login", "email"]
    throttle_scope = "admin_default"

    def get_permissions(self):
        if self.action in {"grant_staff", "revoke_staff"}:
            return [IsUserPrivilegeAdmin()]
        return [IsUserAdmin()]

    def get_queryset(self):
        """Liste utilisateur avec filtres standards back-office."""
        queryset = super().get_queryset()
        is_active = self.request.query_params.get("is_active")
        is_staff = self.request.query_params.get("is_staff")
        is_verified = self.request.query_params.get("is_verified")

        if is_active in {"true", "false"}:
            queryset = queryset.filter(is_active=(is_active == "true"))
        if is_staff in {"true", "false"}:
            queryset = queryset.filter(is_staff=(is_staff == "true"))
        if is_verified in {"true", "false"}:
            queryset = queryset.filter(is_verified=(is_verified == "true"))
        return queryset

    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, pk=None):
        """Active un compte utilisateur."""
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=["is_active"])
        _audit_admin_action(request, "admin_activate_user", "User", user.id)
        return Response({"status": "activated"})

    @action(detail=True, methods=["post"], url_path="deactivate")
    def deactivate(self, request, pk=None):
        """Desactive un compte utilisateur."""
        user = self.get_object()
        user.is_active = False
        user.save(update_fields=["is_active"])
        _audit_admin_action(request, "admin_deactivate_user", "User", user.id)
        return Response({"status": "deactivated"})

    @action(detail=True, methods=["post"], url_path="verify-email")
    def verify_email(self, request, pk=None):
        """Marque l'email d'un utilisateur comme verifie."""
        user = self.get_object()
        user.is_verified = True
        user.save(update_fields=["is_verified"])
        _audit_admin_action(request, "admin_verify_user", "User", user.id)
        return Response({"status": "verified"})

    @action(detail=True, methods=["post"], url_path="grant-staff")
    def grant_staff(self, request, pk=None):
        """Accorde le statut staff (reserve super admin)."""
        user = self.get_object()
        user.is_staff = True
        user.save(update_fields=["is_staff"])
        _audit_admin_action(request, "admin_grant_staff", "User", user.id)
        return Response({"status": "staff_granted"})

    @action(detail=True, methods=["post"], url_path="revoke-staff")
    def revoke_staff(self, request, pk=None):
        """Retire le statut staff (reserve super admin)."""
        user = self.get_object()
        user.is_staff = False
        user.save(update_fields=["is_staff"])
        _audit_admin_action(request, "admin_revoke_staff", "User", user.id)
        return Response({"status": "staff_revoked"})

    @action(detail=False, methods=["post"], url_path="bulk/actions")
    def bulk_actions(self, request):
        """Execute des operations de masse avec option dry-run."""
        user_ids = request.data.get("user_ids") or []
        operation = request.data.get("operation")
        dry_run = _parse_bool(request.data.get("dry_run"), default=False)
        queryset = User.objects.filter(id__in=user_ids)

        if dry_run:
            return Response({"dry_run": True, "operation": operation, "affected": queryset.count()})

        if operation == "activate":
            updated = queryset.update(is_active=True)
        elif operation == "deactivate":
            updated = queryset.update(is_active=False)
        elif operation == "grant_staff":
            updated = queryset.update(is_staff=True)
        elif operation == "revoke_staff":
            updated = queryset.update(is_staff=False)
        else:
            return Response({"detail": "Unsupported operation."}, status=status.HTTP_400_BAD_REQUEST)

        _audit_admin_action(request, "admin_bulk_user_action", "User", "*", {"operation": operation, "count": updated})
        return Response({"updated": updated})

    @action(detail=True, methods=["post"], url_path="set-roles")
    def set_roles(self, request, pk=None):
        """Assigne plusieurs roles admin a un utilisateur.

        Payload:
        {
            "roles": ["support_admin", "billing_admin"],
            "mode": "replace" | "append"
        }
        """
        user = self.get_object()
        roles = request.data.get("roles") or []
        mode = (request.data.get("mode") or "replace").lower()

        if not isinstance(roles, list):
            return Response({"detail": "roles doit etre une liste."}, status=status.HTTP_400_BAD_REQUEST)

        roles = [str(role).strip() for role in roles if str(role).strip()]
        invalid_roles = sorted([role for role in roles if role not in ADMIN_ROLE_NAMES])
        if invalid_roles:
            return Response(
                {
                    "detail": "Roles invalides.",
                    "invalid_roles": invalid_roles,
                    "allowed_roles": sorted(ADMIN_ROLE_NAMES),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        groups = list(Group.objects.filter(name__in=roles))
        existing_group_names = {group.name for group in groups}
        missing_groups = sorted(set(roles) - existing_group_names)
        if missing_groups:
            return Response(
                {
                    "detail": "Certains groupes de roles n'existent pas encore.",
                    "missing_groups": missing_groups,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if mode == "append":
            user.groups.add(*groups)
        elif mode == "replace":
            # On ne touche qu'aux groupes de roles admin; les autres groupes metier restent intacts.
            admin_groups_qs = Group.objects.filter(name__in=ADMIN_ROLE_NAMES)
            user.groups.remove(*admin_groups_qs)
            user.groups.add(*groups)
        else:
            return Response({"detail": "mode doit etre 'replace' ou 'append'."}, status=status.HTTP_400_BAD_REQUEST)

        effective_roles = sorted(
            user.groups.filter(name__in=ADMIN_ROLE_NAMES).values_list("name", flat=True)
        )

        _audit_admin_action(
            request,
            "admin_set_user_roles",
            "User",
            user.id,
            {"mode": mode, "assigned_roles": roles, "effective_roles": effective_roles},
        )

        return Response(
            {
                "status": "roles_updated",
                "user_id": user.id,
                "effective_roles": effective_roles,
            }
        )


class AdminDocumentViewSet(AdminThrottledViewSet, viewsets.ModelViewSet):
    permission_classes = [IsDocumentReadAdmin]
    serializer_class = AdminDocumentSerializer
    queryset = Document.objects.select_related("owner", "category").prefetch_related("tags").all().order_by("-created_at")
    http_method_names = ["get", "patch", "delete", "head", "options"]
    search_fields = ["title", "description", "owner__email"]
    ordering_fields = ["created_at", "updated_at", "title", "date_expiration"]
    throttle_scope = "admin_default"

    def get_permissions(self):
        if self.request.method in SAFE_METHODS and self.action not in {"archive", "restore", "bulk_actions"}:
            return [IsDocumentReadAdmin()]
        return [IsDocumentAdmin()]

    def get_queryset(self):
        queryset = super().get_queryset()
        owner_id = self.request.query_params.get("owner_id")
        archived = self.request.query_params.get("archived")
        expiration_from = self.request.query_params.get("expiration_from")
        expiration_to = self.request.query_params.get("expiration_to")
        if owner_id:
            queryset = queryset.filter(owner_id=owner_id)
        if archived in {"true", "false"}:
            queryset = queryset.filter(archived=(archived == "true"))
        if expiration_from:
            queryset = queryset.filter(date_expiration__gte=expiration_from)
        if expiration_to:
            queryset = queryset.filter(date_expiration__lte=expiration_to)
        return queryset

    @action(detail=True, methods=["post"], url_path="archive")
    def archive(self, request, pk=None):
        document = self.get_object()
        document.archived = True
        document.save(update_fields=["archived"])
        _audit_admin_action(request, "admin_archive_document", "Document", document.id)
        return Response({"status": "archived"})

    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, pk=None):
        document = self.get_object()
        document.archived = False
        document.save(update_fields=["archived"])
        _audit_admin_action(request, "admin_restore_document", "Document", document.id)
        return Response({"status": "restored"})

    @action(detail=False, methods=["post"], url_path="bulk/actions")
    def bulk_actions(self, request):
        doc_ids = request.data.get("document_ids") or []
        operation = request.data.get("operation")
        dry_run = _parse_bool(request.data.get("dry_run"), default=False)
        queryset = Document.objects.filter(id__in=doc_ids)

        if dry_run:
            return Response({"dry_run": True, "operation": operation, "affected": queryset.count()})

        if operation == "archive":
            updated = queryset.update(archived=True)
        elif operation == "restore":
            updated = queryset.update(archived=False)
        elif operation == "delete":
            updated = queryset.count()
            queryset.delete()
        else:
            return Response({"detail": "Unsupported operation."}, status=status.HTTP_400_BAD_REQUEST)

        _audit_admin_action(request, "admin_bulk_document_action", "Document", "*", {"operation": operation, "count": updated})
        return Response({"updated": updated})


class AdminDocumentFileViewSet(AdminThrottledViewSet, viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsDocumentReadAdmin]
    serializer_class = AdminDocumentFileSerializer
    queryset = DocumentFile.objects.select_related("document").all().order_by("-uploaded_at")
    throttle_scope = "admin_default"


class AdminDefaultCategoryViewSet(AdminThrottledViewSet, viewsets.ModelViewSet):
    permission_classes = [IsTaxonomyAdmin]
    serializer_class = AdminDefaultCategorySerializer
    queryset = Category.objects.filter(is_default=True, owner__isnull=True).order_by("name")
    throttle_scope = "admin_default"

    def perform_create(self, serializer):
        instance = serializer.save(is_default=True, owner=None)
        _audit_admin_action(self.request, "admin_create_default_category", "Category", instance.id)


class AdminDefaultTagViewSet(AdminThrottledViewSet, viewsets.ModelViewSet):
    permission_classes = [IsTaxonomyAdmin]
    serializer_class = AdminDefaultTagSerializer
    queryset = Tag.objects.filter(is_default=True, owner__isnull=True).order_by("name")
    throttle_scope = "admin_default"

    def perform_create(self, serializer):
        instance = serializer.save(is_default=True, owner=None)
        _audit_admin_action(self.request, "admin_create_default_tag", "Tag", instance.id)


class AdminReminderViewSet(AdminThrottledViewSet, viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsReminderAdmin]
    serializer_class = AdminReminderSerializer
    queryset = Reminder.objects.select_related("owner", "document").all().order_by("next_run")
    throttle_scope = "admin_default"
    def get_throttles(self):
        if self.action == "trigger":
            self.throttle_scope = "admin_sensitive"
        return super().get_throttles()


    @action(detail=False, methods=["post"], url_path="trigger")
    def trigger(self, request):
        reminder_ids = request.data.get("reminder_ids") or []
        queryset = Reminder.objects.filter(enabled=True)
        if reminder_ids:
            queryset = queryset.filter(id__in=reminder_ids)

        dispatched = []
        for reminder in queryset:
            enqueue_reminder_email(reminder.pk)
            dispatched.append(reminder.pk)

        _audit_admin_action(request, "admin_trigger_reminders", "Reminder", "*", {"count": len(dispatched)})
        return Response({"triggered_reminder_ids": dispatched})


class AdminReminderLogViewSet(AdminThrottledViewSet, viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsReminderAdmin]
    serializer_class = AdminReminderLogSerializer
    queryset = ReminderLog.objects.select_related("reminder").all().order_by("-created_at")
    throttle_scope = "admin_default"


class AdminJobsView(AdminThrottledAPIView):
    permission_classes = [IsReminderAdmin]
    throttle_scope = "admin_sensitive"

    def post(self, request):
        delay_fn = getattr(schedule_due_reminders_task, "delay", None)
        result = delay_fn() if callable(delay_fn) else schedule_due_reminders_task()
        task_id = getattr(result, "id", None)
        _audit_admin_action(request, "admin_schedule_due_reminders", "Job", task_id or "sync")
        return Response({"task_id": task_id, "status": "started"})


class AdminJobStatusView(AdminThrottledAPIView):
    permission_classes = [IsReminderAdmin]
    throttle_scope = "admin_default"

    def get(self, request, task_id):
        try:
            from celery.result import AsyncResult

            result = AsyncResult(task_id)
            return Response({"task_id": task_id, "state": result.state, "result": result.result})
        except Exception as exc:
            return Response({"task_id": task_id, "state": "unknown", "detail": str(exc)})


class AdminAuditLogViewSet(AdminThrottledViewSet, viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuditAdmin]
    serializer_class = AdminAuditLogSerializer
    queryset = AuditLog.objects.select_related("user").all().order_by("-timestamp")
    search_fields = ["action", "target_type", "target_id", "user__email"]
    throttle_scope = "admin_default"

    def get_throttles(self):
        if self.action == "export":
            self.throttle_scope = "admin_export"
        return super().get_throttles()

    def get_queryset(self):
        queryset = super().get_queryset()
        action_name = self.request.query_params.get("action")
        user_id = self.request.query_params.get("user_id")
        target_type = self.request.query_params.get("target_type")
        from_date = self.request.query_params.get("from")
        to_date = self.request.query_params.get("to")

        if action_name:
            queryset = queryset.filter(action=action_name)
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        if target_type:
            queryset = queryset.filter(target_type=target_type)
        if from_date:
            queryset = queryset.filter(timestamp__date__gte=from_date)
        if to_date:
            queryset = queryset.filter(timestamp__date__lte=to_date)
        return queryset

    @action(detail=False, methods=["get"], url_path="export")
    def export(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="audit_logs.csv"'

        writer = csv.writer(response)
        writer.writerow(["id", "timestamp", "user", "action", "target_type", "target_id", "meta"])
        for log in queryset.iterator():
            writer.writerow([
                log.id,
                log.timestamp.isoformat(),
                getattr(log.user, "email", ""),
                log.action,
                log.target_type,
                log.target_id,
                log.meta,
            ])
        return response

    @action(detail=False, methods=["post"], url_path="export-request")
    def export_request(self, request):
        filters = {
            "action": request.data.get("action"),
            "user_id": request.data.get("user_id"),
            "target_type": request.data.get("target_type"),
            "from": request.data.get("from"),
            "to": request.data.get("to"),
        }
        filters = {k: v for k, v in filters.items() if v not in (None, "")}

        delay_fn = getattr(export_audit_logs_task, "delay", None)
        if callable(delay_fn):
            task = delay_fn(actor_id=request.user.id, filters=filters)
            task_id = getattr(task, "id", None)
            _audit_admin_action(request, "admin_export_audit_logs_async", "AuditLog", "*", {"filters": filters, "task_id": task_id})
            return Response({"task_id": task_id, "status": "scheduled"}, status=status.HTTP_202_ACCEPTED)

        result = export_audit_logs_task(actor_id=request.user.id, filters=filters)
        _audit_admin_action(request, "admin_export_audit_logs_sync", "AuditLog", "*", {"filters": filters})
        return Response({"status": "completed", "result": result})


class AdminSubscriptionViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsBillingAdmin]
    serializer_class = AdminSubscriptionSerializer
    queryset = Subscription.objects.select_related("user").all().order_by("-updated_at")
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "admin_default"

    def get_queryset(self):
        queryset = super().get_queryset()
        plan = self.request.query_params.get("plan")
        status_value = self.request.query_params.get("status")
        if plan:
            queryset = queryset.filter(plan=plan)
        if status_value:
            queryset = queryset.filter(status=status_value)
        return queryset

    @action(detail=True, methods=["post"], url_path="sync-stripe")
    def sync_stripe(self, request, pk=None):
        subscription = self.get_object()
        _audit_admin_action(request, "admin_sync_subscription_stripe", "Subscription", subscription.id)
        return Response({
            "detail": "Sync hook acknowledged. Implement Stripe fetch workflow here if needed.",
            "subscription_id": subscription.id,
        })


class AdminCloudProviderViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsCloudAdmin]
    serializer_class = AdminCloudStorageProviderSerializer
    queryset = CloudStorageProvider.objects.all().order_by("name")
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "admin_default"


class AdminCloudConnectionViewSet(AdminThrottledViewSet, viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsCloudAdmin]
    serializer_class = AdminCloudConnectionSerializer
    queryset = UserCloudStorage.objects.select_related("user", "provider").all().order_by("-created_at")
    throttle_scope = "admin_default"

    def get_queryset(self):
        queryset = super().get_queryset()
        user_id = self.request.query_params.get("user_id")
        provider_code = self.request.query_params.get("provider")
        is_active = self.request.query_params.get("is_active")
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        if provider_code:
            queryset = queryset.filter(provider__code=provider_code)
        if is_active in {"true", "false"}:
            queryset = queryset.filter(is_active=(is_active == "true"))
        return queryset

    def get_throttles(self):
        if self.action in {"force_disable", "sync_quota"}:
            self.throttle_scope = "admin_sensitive"
        return super().get_throttles()

    @action(detail=True, methods=["post"], url_path="force-disable")
    def force_disable(self, request, pk=None):
        connection = self.get_object()
        connection.is_active = False
        connection.save(update_fields=["is_active"])
        _audit_admin_action(request, "admin_force_disable_cloud_connection", "UserCloudStorage", connection.id)
        return Response({"status": "disabled"})

    @action(detail=True, methods=["post"], url_path="sync-quota")
    def sync_quota(self, request, pk=None):
        connection = self.get_object()
        try:
            from cors.storage.factory import CloudStorageFactory
            from cors.storage.token_manager import TokenManager

            if not TokenManager.ensure_valid_token(connection):
                return Response({"detail": "Token refresh failed."}, status=status.HTTP_400_BAD_REQUEST)
            backend = CloudStorageFactory.get_backend(connection)
            quota = backend.get_quota_info()

            connection.total_space = quota.get("total_space")
            connection.used_space = quota.get("used_space")
            connection.last_sync = timezone.now()
            connection.save(update_fields=["total_space", "used_space", "last_sync"])

            return Response({"status": "synced", "quota": quota})
        except Exception as exc:
            return Response({"status": "error", "detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminCloudActivityViewSet(AdminThrottledViewSet, viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsCloudAdmin]
    serializer_class = AdminCloudActivitySerializer
    queryset = CloudStorageActivity.objects.select_related("user_storage").all().order_by("-timestamp")
    throttle_scope = "admin_default"


class AdminSystemSettingsView(AdminThrottledAPIView):
    permission_classes = [IsSystemAdmin]
    throttle_scope = "admin_sensitive"

    def get(self, request):
        payload = {
            "debug": settings.DEBUG,
            "allowed_hosts": settings.ALLOWED_HOSTS,
            "page_size": settings.REST_FRAMEWORK.get("PAGE_SIZE"),
            "cloud_storage_enabled": getattr(settings, "CLOUD_STORAGE_ENABLED", False),
            "email_backend": getattr(settings, "EMAIL_BACKEND", ""),
        }
        return Response(payload)

    def patch(self, request):
        return Response(
            {
                "detail": "Runtime settings update is intentionally disabled."
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class AdminRolesView(AdminThrottledAPIView):
    """Expose la matrice roles -> capacites pour le front admin."""

    permission_classes = [IsSystemAdmin]
    throttle_scope = "admin_default"

    def get(self, request):
        return Response(
            {
                "roles": sorted(ADMIN_ROLE_NAMES),
                "capabilities": ADMIN_ROLE_CAPABILITIES,
            }
        )


class AdminIntegrationTestView(AdminThrottledAPIView):
    permission_classes = [IsSystemAdmin]
    throttle_scope = "admin_integrations"

    def post(self, request, name):
        _enforce_local_rate_limit(request, "admin_integrations", "admin_integrations")

        checks = {
            "stripe": bool(getattr(settings, "STRIPE_SECRET_KEY", "")),
            "email": bool(getattr(settings, "EMAIL_HOST", "")),
            "celery": bool(getattr(settings, "CELERY_BROKER_URL", "")),
        }
        if name not in checks:
            return Response({"detail": "Unknown integration."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"integration": name, "configured": checks[name]})
