from django.core.management.base import BaseCommand

from courses.exams import ensure_exam
from courses.models import Course


class Command(BaseCommand):
    help = "Create the Full Module Exam for every course that lacks one (use --refresh to rebuild existing exams from the lesson quizzes)."

    def add_arguments(self, parser):
        parser.add_argument("--refresh", action="store_true", help="Rebuild existing exams too")

    def handle(self, *args, **options):
        for course in Course.objects.all():
            exam, action = ensure_exam(course, refresh=options["refresh"])
            self.stdout.write(f"{course.title}: {action or 'no quiz questions to build from'}")
