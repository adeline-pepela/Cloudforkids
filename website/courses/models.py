from django.conf import settings
from django.db import models
from django.urls import reverse


class Tier(models.Model):
    """The three programme tiers: Foundational, Intermediate, Advanced."""

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    grade_range = models.CharField(max_length=50, help_text="e.g. Grade 4-6")
    cbc_alignment = models.CharField(max_length=200, blank=True, help_text="CBC/CBE subject alignment")
    summary = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=10, default="\u2601\ufe0f", help_text="Emoji icon")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("courses:programs") + f"#{self.slug}"


class Course(models.Model):
    tier = models.ForeignKey(Tier, on_delete=models.CASCADE, related_name="courses")
    title = models.CharField(max_length=150)
    slug = models.SlugField(unique=True)
    summary = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=10, default="\U0001F4E6")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["tier__order", "order"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("courses:course_detail", args=[self.slug])

    @property
    def lesson_count(self):
        return self.lessons.count()


class Lesson(models.Model):
    class LessonType(models.TextChoices):
        LESSON = "lesson", "Lesson"
        EXAM = "exam", "Module Exam"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="lessons")
    title = models.CharField(max_length=150)
    slug = models.SlugField()
    summary = models.CharField(max_length=300, blank=True)
    content = models.TextField(help_text="Lesson content (supports plain text / simple markup)")
    duration_minutes = models.PositiveIntegerField(default=30)
    order = models.PositiveIntegerField(default=0)
    lesson_type = models.CharField(
        max_length=10, choices=LessonType.choices, default=LessonType.LESSON,
        help_text="Regular lesson, or the full module exam for the course",
    )
    pass_score_percent = models.PositiveIntegerField(
        default=70, help_text="Score (%) needed to pass this item's quiz/exam, if it has one"
    )

    class Meta:
        ordering = ["course__tier__order", "course__order", "order"]
        unique_together = ("course", "slug")

    def __str__(self):
        return f"{self.course.title} - {self.title}"

    def get_absolute_url(self):
        return reverse("courses:lesson_detail", args=[self.course.slug, self.slug])

    @property
    def is_exam(self):
        return self.lesson_type == self.LessonType.EXAM

    def next_lesson(self):
        return Lesson.objects.filter(course=self.course, order__gt=self.order).order_by("order").first()

    def previous_lesson(self):
        return Lesson.objects.filter(course=self.course, order__lt=self.order).order_by("-order").first()


class Enrollment(models.Model):
    learner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="enrollments")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("learner", "course")
        ordering = ["-enrolled_at"]

    def __str__(self):
        return f"{self.learner} -> {self.course}"

    @property
    def completed_lesson_ids(self):
        return set(
            LessonCompletion.objects.filter(enrollment=self).values_list("lesson_id", flat=True)
        )

    @property
    def progress_percent(self):
        total = self.course.lesson_count
        if not total:
            return 0
        done = LessonCompletion.objects.filter(enrollment=self).count()
        return round((done / total) * 100)

    @property
    def is_complete(self):
        return self.course.lesson_count > 0 and self.progress_percent == 100


class LessonCompletion(models.Model):
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="completions")
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="completions")
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("enrollment", "lesson")


class Badge(models.Model):
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=250)
    icon = models.CharField(max_length=10, default="\U0001F3C6")
    criteria = models.CharField(
        max_length=250, blank=True, help_text="Human-readable note on how this badge is earned"
    )

    def __str__(self):
        return self.name


class LearnerBadge(models.Model):
    learner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="badges")
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name="awarded_to")
    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("learner", "badge")
        ordering = ["-earned_at"]

    def __str__(self):
        return f"{self.learner} earned {self.badge}"
