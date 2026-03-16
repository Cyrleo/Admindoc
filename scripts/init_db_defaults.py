#!/usr/bin/env python3
"""Initialize database tables and seed default categories and tags.

Usage:
  python scripts/init_db_defaults.py
  python scripts/init_db_defaults.py --skip-migrate
"""

import argparse
import os
import sys
from pathlib import Path


DEFAULT_CATEGORIES = [
    {"name": "Factures", "color": "#2563EB", "icon": "receipt"},
    {"name": "Contrats", "color": "#059669", "icon": "file-text"},
    {"name": "Identite", "color": "#7C3AED", "icon": "id-card"},
    {"name": "Assurances", "color": "#DC2626", "icon": "shield"},
    {"name": "Banque", "color": "#D97706", "icon": "landmark"},
    {"name": "Sante", "color": "#DB2777", "icon": "heart-pulse"},
    {"name": "Administratif", "color": "#0F766E", "icon": "folder"},
]

DEFAULT_TAGS = [
    "Urgent",
    "A classer",
    "A renouveler",
    "Personnel",
    "Professionnel",
    "Archive",
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
                "color": item["color"],
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

    for tag_name in DEFAULT_TAGS:
        _, created = Tag.objects.update_or_create(
            owner=None,
            name=tag_name,
            defaults={
                "is_default": True,
            },
        )
        if created:
            created_count += 1
        else:
            updated_count += 1

    return created_count, updated_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create DB tables and default categories and tags for AdminDoc."
    )
    parser.add_argument(
        "--skip-migrate",
        action="store_true",
        help="Skip migration step and only seed default categories and tags.",
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

    print(
        "Done. "
        f"Categories -> Created: {categories_created}, Updated: {categories_updated}. "
        f"Tags -> Created: {tags_created}, Updated: {tags_updated}"
    )


if __name__ == "__main__":
    main()
