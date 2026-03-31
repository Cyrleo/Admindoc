"""
Script to migrate existing Document.file data to DocumentFile model.
This creates a DocumentFile entry for each Document that has a file attached.
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'doc.settings')
django.setup()

from cors.models import Document, DocumentFile


def migrate_documents_to_files():
    """
    Migrate existing Document.file fields to DocumentFile entries.
    """
    # Find all documents that have a file but no DocumentFile entries
    documents_with_files = Document.objects.filter(file__isnull=False).exclude(file='')
    
    migrated_count = 0
    skipped_count = 0
    
    for document in documents_with_files:
        # Check if this document already has files migrated
        if document.files.exists():
            print(f"⏭️  Skipping document {document.id} - already has files")
            skipped_count += 1
            continue
        
        # Create a DocumentFile entry from the old file field
        try:
            document_file = DocumentFile.objects.create(
                document=document,
                file=document.file,  # This copies the file reference
                file_name=document.file_name or document.file.name.split('/')[-1],
                mime_type=document.mime_type or '',
                size=document.size or document.file.size,
                is_primary=True,  # First file is primary
            )
            
            print(f"✅ Migrated document {document.id}: {document.title} -> {document_file.file_name}")
            migrated_count += 1
            
        except Exception as e:
            print(f"❌ Error migrating document {document.id}: {e}")
    
    print(f"\n🎉 Migration complete!")
    print(f"   Migrated: {migrated_count}")
    print(f"   Skipped: {skipped_count}")
    print(f"   Total processed: {migrated_count + skipped_count}")
    
    return migrated_count, skipped_count


if __name__ == '__main__':
    print("=" * 60)
    print("Starting Document File Migration")
    print("=" * 60)
    migrate_documents_to_files()
