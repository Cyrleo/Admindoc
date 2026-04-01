"""Permissions RBAC de l'API d'administration.

Le principe est simple:
- Un utilisateur doit etre staff pour entrer dans l'API admin.
- Ses groupes Django determinent ensuite les domaines autorises.
- Un utilisateur peut cumuler plusieurs roles en etant membre de plusieurs groupes.
"""

from rest_framework.permissions import BasePermission


ROLE_SUPER_ADMIN = "super_admin"
ROLE_SUPPORT_ADMIN = "support_admin"
ROLE_BILLING_ADMIN = "billing_admin"
ROLE_CONTENT_ADMIN = "content_admin"
ROLE_OPS_ADMIN = "ops_admin"

ADMIN_ROLE_NAMES = {
    ROLE_SUPER_ADMIN,
    ROLE_SUPPORT_ADMIN,
    ROLE_BILLING_ADMIN,
    ROLE_CONTENT_ADMIN,
    ROLE_OPS_ADMIN,
}

ADMIN_ROLE_CAPABILITIES = {
    ROLE_SUPER_ADMIN: [
        "acces complet admin",
    ],
    ROLE_SUPPORT_ADMIN: [
        "dashboard lecture",
        "utilisateurs gestion",
        "documents lecture",
        "audit lecture/export",
    ],
    ROLE_BILLING_ADMIN: [
        "dashboard lecture",
        "subscriptions gestion",
    ],
    ROLE_CONTENT_ADMIN: [
        "dashboard lecture",
        "documents gestion",
        "taxonomy gestion",
    ],
    ROLE_OPS_ADMIN: [
        "dashboard lecture",
        "documents gestion",
        "reminders/jobs",
        "cloud operations",
        "system checks",
        "audit lecture/export",
    ],
}


def get_admin_roles(user):
    """Retourne l'ensemble des roles admin portes par l'utilisateur."""
    if not user or not getattr(user, "is_authenticated", False):
        return set()
    group_names = set(user.groups.values_list("name", flat=True))
    return {
        role
        for role in ADMIN_ROLE_NAMES
        if role in group_names
    }


class IsAdminApiUser(BasePermission):
    """Base admin gate: authenticated staff user."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and getattr(user, "is_staff", False))


class RoleBasedAdminPermission(IsAdminApiUser):
    """Permission de base orientee roles.

    Un utilisateur superuser est autorise partout.
    Sinon, au moins un role de l'utilisateur doit appartenir a `allowed_roles`.
    """
    allowed_roles = set()

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False

        user = request.user
        if user.is_superuser:
            return True

        roles = get_admin_roles(user)
        return bool(roles.intersection(self.allowed_roles))


class IsDashboardAdmin(RoleBasedAdminPermission):
    allowed_roles = {
        ROLE_SUPER_ADMIN,
        ROLE_SUPPORT_ADMIN,
        ROLE_BILLING_ADMIN,
        ROLE_CONTENT_ADMIN,
        ROLE_OPS_ADMIN,
    }


class IsUserAdmin(RoleBasedAdminPermission):
    allowed_roles = {ROLE_SUPER_ADMIN, ROLE_SUPPORT_ADMIN}


class IsUserPrivilegeAdmin(RoleBasedAdminPermission):
    allowed_roles = {ROLE_SUPER_ADMIN}


class IsDocumentReadAdmin(RoleBasedAdminPermission):
    allowed_roles = {ROLE_SUPER_ADMIN, ROLE_SUPPORT_ADMIN, ROLE_CONTENT_ADMIN, ROLE_OPS_ADMIN}


class IsDocumentAdmin(RoleBasedAdminPermission):
    allowed_roles = {ROLE_SUPER_ADMIN, ROLE_CONTENT_ADMIN, ROLE_OPS_ADMIN}


class IsTaxonomyAdmin(RoleBasedAdminPermission):
    allowed_roles = {ROLE_SUPER_ADMIN, ROLE_CONTENT_ADMIN}


class IsReminderAdmin(RoleBasedAdminPermission):
    allowed_roles = {ROLE_SUPER_ADMIN, ROLE_OPS_ADMIN}


class IsAuditAdmin(RoleBasedAdminPermission):
    allowed_roles = {ROLE_SUPER_ADMIN, ROLE_SUPPORT_ADMIN, ROLE_OPS_ADMIN}


class IsBillingAdmin(RoleBasedAdminPermission):
    allowed_roles = {ROLE_SUPER_ADMIN, ROLE_BILLING_ADMIN}


class IsCloudAdmin(RoleBasedAdminPermission):
    allowed_roles = {ROLE_SUPER_ADMIN, ROLE_OPS_ADMIN}


class IsSystemAdmin(RoleBasedAdminPermission):
    allowed_roles = {ROLE_SUPER_ADMIN, ROLE_OPS_ADMIN}
