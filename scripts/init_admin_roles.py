"""Initialize admin role groups for the admin API permission model.

Usage:
  source venv/bin/activate
  python scripts/init_admin_roles.py
"""

import os
import sys

import django


ROLE_DEFINITIONS = {
    "super_admin": [
        "all admin API permissions (full access)",
    ],
    "support_admin": [
        "dashboard read",
        "users management",
        "documents read",
        "audit logs read/export",
    ],
    "billing_admin": [
        "dashboard read",
        "subscriptions management",
        "billing related checks",
    ],
    "content_admin": [
        "dashboard read",
        "documents management",
        "default categories/tags management",
    ],
    "ops_admin": [
        "dashboard read",
        "documents management",
        "reminders and jobs",
        "cloud providers/connections/activities",
        "system checks",
        "audit logs read/export",
    ],
}


def bootstrap_django():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, project_root)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "doc.settings")
    django.setup()


def create_groups():
    from django.contrib.auth.models import Group

    created = []
    existing = []

    for role_name in ROLE_DEFINITIONS:
        group, was_created = Group.objects.get_or_create(name=role_name)
        if was_created:
            created.append(group.name)
        else:
            existing.append(group.name)

    return created, existing


def main():
    bootstrap_django()
    created, existing = create_groups()

    print("Admin role initialization complete")
    print(f"Created groups: {created}")
    print(f"Existing groups: {existing}")
    print("\nRole guide:")
    for role, capabilities in ROLE_DEFINITIONS.items():
        print(f"- {role}")
        for capability in capabilities:
            print(f"  * {capability}")


if __name__ == "__main__":
    main()
