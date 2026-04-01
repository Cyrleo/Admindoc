from django.urls import include, path
from rest_framework.routers import DefaultRouter

from cors.pages.admin_api.views import (
    AdminAuditLogViewSet,
    AdminCloudActivityViewSet,
    AdminCloudConnectionViewSet,
    AdminCloudProviderViewSet,
    AdminDashboardActivityFeedView,
    AdminDashboardHealthView,
    AdminDashboardKpisView,
    AdminDashboardOverviewView,
    AdminDefaultCategoryViewSet,
    AdminDefaultTagViewSet,
    AdminDocumentFileViewSet,
    AdminDocumentViewSet,
    AdminIntegrationTestView,
    AdminJobsView,
    AdminJobStatusView,
    AdminReminderLogViewSet,
    AdminReminderViewSet,
    AdminRolesView,
    AdminSubscriptionViewSet,
    AdminSystemSettingsView,
    AdminUserViewSet,
)

router = DefaultRouter()

# Routes REST principales du back-office admin.
router.register(r"users", AdminUserViewSet, basename="admin-users")
router.register(r"documents", AdminDocumentViewSet, basename="admin-documents")
router.register(r"document-files", AdminDocumentFileViewSet, basename="admin-document-files")
router.register(r"default-categories", AdminDefaultCategoryViewSet, basename="admin-default-categories")
router.register(r"default-tags", AdminDefaultTagViewSet, basename="admin-default-tags")
router.register(r"reminders", AdminReminderViewSet, basename="admin-reminders")
router.register(r"reminder-logs", AdminReminderLogViewSet, basename="admin-reminder-logs")
router.register(r"audit-logs", AdminAuditLogViewSet, basename="admin-audit-logs")
router.register(r"subscriptions", AdminSubscriptionViewSet, basename="admin-subscriptions")
router.register(r"cloud/providers", AdminCloudProviderViewSet, basename="admin-cloud-providers")
router.register(r"cloud/connections", AdminCloudConnectionViewSet, basename="admin-cloud-connections")
router.register(r"cloud/activities", AdminCloudActivityViewSet, basename="admin-cloud-activities")

urlpatterns = [
    # Endpoints dashboard/monitoring admin.
    path("dashboard/overview/", AdminDashboardOverviewView.as_view(), name="admin-dashboard-overview"),
    path("dashboard/kpis/", AdminDashboardKpisView.as_view(), name="admin-dashboard-kpis"),
    path("dashboard/health/", AdminDashboardHealthView.as_view(), name="admin-dashboard-health"),
    path("dashboard/activity-feed/", AdminDashboardActivityFeedView.as_view(), name="admin-dashboard-activity-feed"),

    # Endpoints operations systeme et jobs.
    path("jobs/reminders/schedule-due/", AdminJobsView.as_view(), name="admin-jobs-reminders-schedule-due"),
    path("jobs/status/<str:task_id>/", AdminJobStatusView.as_view(), name="admin-jobs-status"),
    path("system/settings/", AdminSystemSettingsView.as_view(), name="admin-system-settings"),
    path("system/roles/", AdminRolesView.as_view(), name="admin-system-roles"),
    path("system/integrations/<str:name>/test/", AdminIntegrationTestView.as_view(), name="admin-system-integrations-test"),

    # Toutes les routes generees automatiquement par DRF Router.
    path("", include(router.urls)),
]
