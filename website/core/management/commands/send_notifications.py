from django.core.management.base import BaseCommand

from core import notify


class Command(BaseCommand):
    help = "Send scheduled emails: weekly parent summaries and reminders for learners who have gone quiet. Run daily from a scheduler."

    def add_arguments(self, parser):
        parser.add_argument("--weekly", action="store_true", help="Send the weekly progress summary to parents (once per week each)")
        parser.add_argument("--nudges", action="store_true", help="Send reminders to learners and parents after a few quiet days")
        parser.add_argument("--days", type=int, default=4, help="Days without activity before a reminder (default 4)")
        parser.add_argument("--dry-run", action="store_true", help="Only count who would get an email")

    def handle(self, *args, **options):
        if not options["weekly"] and not options["nudges"]:
            self.stderr.write("Choose --weekly and/or --nudges.")
            return
        dry = options["dry_run"]
        if options["weekly"]:
            self.stdout.write(f"Weekly summaries: {notify.run_weekly_summaries(dry_run=dry)}{' (dry run)' if dry else ' sent'}")
        if options["nudges"]:
            self.stdout.write(f"Reminders: {notify.run_nudges(days=options['days'], dry_run=dry)}{' (dry run)' if dry else ' sent'}")
