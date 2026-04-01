from django.urls import include, path

urlpatterns = [
    path("categories/",     include("cors.pages.category.urls")),
    path("tags/",           include("cors.pages.tag.urls")),
    path("documents/",      include("cors.pages.document.urls")),
    path("reminders/",      include("cors.pages.reminder.urls")),
    path("shared-links/",   include("cors.pages.shared_link.urls")),
    path("audit-logs/",     include("cors.pages.audit_log.urls")),
    path("billing/",        include("cors.pages.billing.urls")),
    path("cloud-storage/",  include("cors.pages.cloud_storage.urls")),
]
