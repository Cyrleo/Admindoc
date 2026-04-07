"""Tests de la couche admin RBAC et throttling."""

# pyright: reportAttributeAccessIssue=false

from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from cors.models import AuditLog, Document, DocumentFile, SharedLink
from cors.pages.admin_api.permissions import (
	ROLE_BILLING_ADMIN,
	ROLE_OPS_ADMIN,
	ROLE_SUPPORT_ADMIN,
)
from cors.utils.audit import make_json_safe


class AdminApiRBACTests(TestCase):
	"""Tests fonctionnels de la couche admin RBAC."""

	def setUp(self):
		self.client = APIClient()

		# Groupes de roles admin utilises dans les tests.
		self.support_group = Group.objects.create(name=ROLE_SUPPORT_ADMIN)
		self.billing_group = Group.objects.create(name=ROLE_BILLING_ADMIN)
		self.ops_group = Group.objects.create(name=ROLE_OPS_ADMIN)

		self.super_admin = User.objects.create_user(
			email="super@admindoc.test",
			password="testpass123",
			is_staff=True,
			is_superuser=True,
		)

		self.support_admin = User.objects.create_user(
			email="support@admindoc.test",
			password="testpass123",
			is_staff=True,
		)
		self.support_admin.groups.add(self.support_group)

		self.billing_admin = User.objects.create_user(
			email="billing@admindoc.test",
			password="testpass123",
			is_staff=True,
		)
		self.billing_admin.groups.add(self.billing_group)

		self.user_target = User.objects.create_user(
			email="user-target@admindoc.test",
			password="testpass123",
			is_staff=False,
		)

		self.doc_owner = User.objects.create_user(
			email="owner@admindoc.test",
			password="testpass123",
		)
		self.document = Document.objects.create(owner=self.doc_owner, title="Doc Test")

	def _auth(self, user):
		self.client.force_authenticate(user=user)

	def test_billing_admin_cannot_access_users_endpoint(self):
		self._auth(self.billing_admin)
		response = self.client.get("/api/admin/v1/users/")
		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

	def test_support_admin_can_read_users_endpoint(self):
		self._auth(self.support_admin)
		response = self.client.get("/api/admin/v1/users/")
		self.assertEqual(response.status_code, status.HTTP_200_OK)

	def test_set_roles_replace_allows_multiple_roles(self):
		self._auth(self.super_admin)
		response = self.client.post(
			f"/api/admin/v1/users/{self.user_target.id}/set-roles/",
			{"roles": [ROLE_SUPPORT_ADMIN, ROLE_BILLING_ADMIN], "mode": "replace"},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.user_target.refresh_from_db()
		names = set(self.user_target.groups.values_list("name", flat=True))
		self.assertEqual(names, {ROLE_SUPPORT_ADMIN, ROLE_BILLING_ADMIN})

	def test_set_roles_append_keeps_existing_roles(self):
		self.user_target.groups.add(self.support_group)
		self._auth(self.super_admin)
		response = self.client.post(
			f"/api/admin/v1/users/{self.user_target.id}/set-roles/",
			{"roles": [ROLE_OPS_ADMIN], "mode": "append"},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.user_target.refresh_from_db()
		names = set(self.user_target.groups.values_list("name", flat=True))
		self.assertEqual(names, {ROLE_SUPPORT_ADMIN, ROLE_OPS_ADMIN})

	def test_support_admin_cannot_modify_document(self):
		self._auth(self.support_admin)
		response = self.client.post(
			f"/api/admin/v1/documents/{self.document.id}/archive/",
			{},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

	def test_roles_endpoint_returns_capability_matrix(self):
		self._auth(self.super_admin)
		response = self.client.get("/api/admin/v1/system/roles/")
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		payload = response.json()
		self.assertIn("roles", payload)
		self.assertIn("capabilities", payload)
		self.assertIn(ROLE_SUPPORT_ADMIN, payload["roles"])


class AdminApiThrottleTests(TestCase):
	"""Validation simple des scopes de throttling admin."""

	def setUp(self):
		self.client = APIClient()
		self.ops_group = Group.objects.create(name=ROLE_OPS_ADMIN)
		self.user = User.objects.create_user(
			email="ops-throttle@admindoc.test",
			password="testpass123",
			is_staff=True,
		)
		self.user.groups.add(self.ops_group)

	@override_settings(
		REST_FRAMEWORK={
			"DEFAULT_AUTHENTICATION_CLASSES": (
				"rest_framework_simplejwt.authentication.JWTAuthentication",
			),
			"DEFAULT_PERMISSION_CLASSES": (
				"rest_framework.permissions.AllowAny",
			),
			"DEFAULT_FILTER_BACKENDS": (
				"django_filters.rest_framework.DjangoFilterBackend",
				"rest_framework.filters.SearchFilter",
				"rest_framework.filters.OrderingFilter",
			),
			"DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
			"DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
			"PAGE_SIZE": 20,
			"DEFAULT_THROTTLE_CLASSES": (
				"rest_framework.throttling.ScopedRateThrottle",
			),
			"DEFAULT_THROTTLE_RATES": {
				"admin_default": "100/min",
				"admin_sensitive": "100/min",
				"admin_export": "100/min",
				"admin_integrations": "2/min",
			},
		}
	)
	def test_admin_integrations_scope_throttles_requests(self):
		cache.clear()
		self.client.force_authenticate(user=self.user)

		url = "/api/admin/v1/system/integrations/email/test/"
		first = self.client.post(url, {}, format="json")
		second = self.client.post(url, {}, format="json")
		third = self.client.post(url, {}, format="json")

		self.assertEqual(first.status_code, status.HTTP_200_OK)
		self.assertEqual(second.status_code, status.HTTP_200_OK)
		self.assertEqual(third.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


class CategoryAuditMetaSerializationTests(TestCase):
	"""Valide que les IDs UUID dans les meta d'audit sont serialisables JSON."""

	def setUp(self):
		self.client = APIClient()
		self.user = User.objects.create_user(
			email="category-owner@admindoc.test",
			password="testpass123",
		)
		self.client.force_authenticate(user=self.user)

	def test_create_category_audit_meta_owner_id_is_string(self):
		response = self.client.post(
			"/api/categories/",
			{"name": "Factures", "icon": "folder"},
			format="json",
		)

		self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
		audit = AuditLog.objects.filter(action="created_category").latest("timestamp")
		self.assertEqual(audit.meta.get("owner_id"), str(self.user.id))
		self.assertIsInstance(audit.meta.get("owner_id"), str)


@override_settings(
	STORAGES={
		"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
		"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
	}
)
class DocumentFileDownloadAuditMetaSerializationTests(TestCase):
	"""Ensure UUID values in download audit meta are JSON serializable."""

	def setUp(self):
		self.client = APIClient()
		self.user = User.objects.create_user(
			email="download-owner@admindoc.test",
			password="testpass123",
		)
		self.client.force_authenticate(user=self.user)

		self.document = Document.objects.create(owner=self.user, title="Passport")
		upload = SimpleUploadedFile("passport.txt", b"file-content", content_type="text/plain")
		self.document_file = DocumentFile.objects.create(
			document=self.document,
			file=upload,
			file_name="passport.txt",
			mime_type="text/plain",
			size=len(b"file-content"),
		)

	def test_download_file_audit_meta_document_id_is_string(self):
		response = self.client.get(f"/api/documents/files/{self.document_file.id}/download/")

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		audit = AuditLog.objects.filter(action="download_document_file").latest("timestamp")
		self.assertEqual(audit.meta.get("document_id"), str(self.document.id))
		self.assertIsInstance(audit.meta.get("document_id"), str)


@override_settings(
	STORAGES={
		"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
		"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
	}
)
class SharedLinkAuditMetaSerializationTests(TestCase):
	"""Ensure public shared-link audit metadata never stores raw UUID values."""

	def setUp(self):
		self.client = APIClient()
		self.owner = User.objects.create_user(
			email="shared-owner@admindoc.test",
			password="testpass123",
		)
		upload = SimpleUploadedFile("shared.txt", b"shared-file", content_type="text/plain")
		self.document = Document.objects.create(owner=self.owner, title="Shared Doc", file=upload)
		self.shared_link = SharedLink.objects.create(document=self.document, creator=self.owner)

	def test_public_download_logs_json_safe_document_id(self):
		response = self.client.get(f"/share/{self.shared_link.token}/")

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		audit = AuditLog.objects.filter(action="download_shared_link").latest("timestamp")
		self.assertEqual(audit.meta.get("document_id"), str(self.document.id))
		self.assertIsInstance(audit.meta.get("document_id"), str)


class AuditJsonSafeUtilityTests(TestCase):
	"""Validate recursive UUID normalization for audit metadata payloads."""

	def test_make_json_safe_converts_nested_uuids(self):
		user = User.objects.create_user(
			email="json-safe@admindoc.test",
			password="testpass123",
		)
		document = Document.objects.create(owner=user, title="Nested UUID")
		payload = {
			"document_id": document.id,
			"items": [document.id, {"owner_id": user.id}],
		}

		normalized = make_json_safe(payload)

		self.assertEqual(normalized["document_id"], str(document.id))
		self.assertEqual(normalized["items"][0], str(document.id))
		self.assertEqual(normalized["items"][1]["owner_id"], str(user.id))


