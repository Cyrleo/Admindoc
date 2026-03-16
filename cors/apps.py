from django.apps import AppConfig


class CorsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cors'

    def ready(self):
        import cors.signals  # noqa: F401
