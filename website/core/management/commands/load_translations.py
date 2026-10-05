from django.core.management.base import BaseCommand

from core.models import UITranslation
from core.translation import clear_cache
from core.translations_sw import SW
from core.translations_sw_content import CONTENT


class Command(BaseCommand):
    help = "Add any Kiswahili wording from the code that is missing in the UI translations table (existing rows are never changed)."

    def handle(self, *args, **options):
        added = 0
        for english, swahili in {**SW, **CONTENT}.items():
            _, created = UITranslation.objects.get_or_create(english=english, defaults={"swahili": swahili})
            added += created
        clear_cache()
        self.stdout.write(f"{added} new translation(s) added, {UITranslation.objects.count()} in total.")
