"""
Module de gestion des backends de stockage cloud.
Auto-initialise les backends au chargement de l'app.
"""

# Auto-register backends
from cors.storage.backends import register_backends
