#!/usr/bin/env python3
"""Initialize database tables and seed defaults (taxonomy + admin groups).

Usage:
  python scripts/init_db_defaults.py
  python scripts/init_db_defaults.py --skip-migrate
"""

import argparse
import os
import sys
from pathlib import Path


DEFAULT_CATEGORIES = [
    {"name": "Factures", "icon": "receipt"},
    {"name": "Contrats", "icon": "file-text"},
    {"name": "Identite", "icon": "id-card"},
    {"name": "Assurances", "icon": "shield"},
    {"name": "Banque", "icon": "landmark"},
    {"name": "Sante", "icon": "heart-pulse"},
    {"name": "Administratif", "icon": "folder"},
]

DEFAULT_TAGS = [
    {"name": "Urgent", "color": "#DC2626"},
    {"name": "A classer", "color": "#2563EB"},
    {"name": "A renouveler", "color": "#D97706"},
    {"name": "Personnel", "color": "#7C3AED"},
    {"name": "Professionnel", "color": "#059669"},
    {"name": "Archive", "color": "#6B7280"},
]


def setup_django() -> None:
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "doc.settings")

    import django

    django.setup()


def run_migrations() -> None:
    from django.core.management import call_command

    call_command("migrate", interactive=False)


def seed_default_categories() -> tuple[int, int]:
    from cors.models import Category

    created_count = 0
    updated_count = 0

    for item in DEFAULT_CATEGORIES:
        _, created = Category.objects.update_or_create(
            owner=None,
            name=item["name"],
            defaults={
                "icon": item["icon"],
                "is_default": True,
            },
        )
        if created:
            created_count += 1
        else:
            updated_count += 1

    return created_count, updated_count


def seed_default_tags() -> tuple[int, int]:
    from cors.models import Tag

    created_count = 0
    updated_count = 0

    for item in DEFAULT_TAGS:
        _, created = Tag.objects.update_or_create(
            owner=None,
            name=item["name"],
            defaults={
                "color": item["color"],
                "is_default": True,
            },
        )
        if created:
            created_count += 1
        else:
            updated_count += 1

    return created_count, updated_count


def seed_admin_groups() -> tuple[int, int]:
    from django.contrib.auth.models import Group
    from cors.pages.admin_api.permissions import ADMIN_ROLE_NAMES

    created_count = 0
    existing_count = 0

    for role_name in sorted(ADMIN_ROLE_NAMES):
        _, created = Group.objects.get_or_create(name=role_name)
        if created:
            created_count += 1
        else:
            existing_count += 1

    return created_count, existing_count


def seed_default_admin_user() -> tuple[bool, str, int]:
    """Create/update a bootstrap admin account and attach all admin role groups.

    Environment variables:
    - INIT_ADMIN_EMAIL (default: admin@admindoc.local)
    - INIT_ADMIN_PASSWORD (default: Admin123!ChangeMe)
    - INIT_ADMIN_FIRST_NAME (default: Admin)
    - INIT_ADMIN_LAST_NAME (default: Root)
    """
    from accounts.models import User
    from django.contrib.auth.models import Group
    from cors.pages.admin_api.permissions import ADMIN_ROLE_NAMES

    email = os.getenv("INIT_ADMIN_EMAIL", "admin@admindoc.local").strip().lower()
    password = os.getenv("INIT_ADMIN_PASSWORD", "Admin123!ChangeMe")
    first_name = os.getenv("INIT_ADMIN_FIRST_NAME", "Admin").strip()
    last_name = os.getenv("INIT_ADMIN_LAST_NAME", "Root").strip()

    user, created = User.objects.get_or_create(
        email=email,
        defaults={
            "first_name": first_name,
            "last_name": last_name,
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
            "is_verified": True,
        },
    )

    if created:
        user.set_password(password)
        user.save(update_fields=["password"])
    else:
        updated = False
        if user.first_name != first_name:
            user.first_name = first_name
            updated = True
        if user.last_name != last_name:
            user.last_name = last_name
            updated = True
        if not user.is_staff:
            user.is_staff = True
            updated = True
        if not user.is_superuser:
            user.is_superuser = True
            updated = True
        if not user.is_active:
            user.is_active = True
            updated = True
        if not user.is_verified:
            user.is_verified = True
            updated = True

        if updated:
            user.save()

    role_groups = list(Group.objects.filter(name__in=sorted(ADMIN_ROLE_NAMES)))
    user.groups.add(*role_groups)

    return created, user.email, len(role_groups)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create DB tables and default categories/tags and admin groups for AdminDoc."
    )
    parser.add_argument(
        "--skip-migrate",
        action="store_true",
        help="Skip migration step and only seed default categories, tags and admin groups.",
    )
    parser.add_argument(
        "--skip-admin-user",
        action="store_true",
        help="Skip creation/update of default bootstrap admin user.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_django()

    if not args.skip_migrate:
        print("Applying migrations...")
        run_migrations()

    print("Seeding default categories...")
    categories_created, categories_updated = seed_default_categories()

    print("Seeding default tags...")
    tags_created, tags_updated = seed_default_tags()

    print("Seeding admin role groups...")
    groups_created, groups_existing = seed_admin_groups()

    admin_user_status = "skipped"
    admin_user_email = ""
    admin_roles_assigned = 0
    if not args.skip_admin_user:
        print("Seeding bootstrap admin user...")
        created, admin_user_email, admin_roles_assigned = seed_default_admin_user()
        admin_user_status = "created" if created else "updated"

    print(
        "Done. "
        f"Categories -> Created: {categories_created}, Updated: {categories_updated}. "
        f"Tags -> Created: {tags_created}, Updated: {tags_updated}. "
        f"Admin groups -> Created: {groups_created}, Existing: {groups_existing}. "
        f"Admin user -> Status: {admin_user_status}, Email: {admin_user_email or '-'}, Roles attached: {admin_roles_assigned}"
    )

    if not os.getenv("INIT_ADMIN_PASSWORD") and not args.skip_admin_user:
        print(
            "WARNING: INIT_ADMIN_PASSWORD not set. "
            "Default password 'Admin123!ChangeMe' was used for newly created admin users."
        )


if __name__ == "__main__":
    main()
