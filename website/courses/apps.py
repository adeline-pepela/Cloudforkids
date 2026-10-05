from django.apps import AppConfig


class CoursesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "courses"

    def ready(self):
        from django.db.models.signals import post_migrate

        from . import signals  # noqa: F401
        from .seeding import seed_if_empty

        post_migrate.connect(seed_if_empty, sender=self, dispatch_uid="courses-first-run-seed")
