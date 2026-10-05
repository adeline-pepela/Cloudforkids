from django.contrib import admin
from django.utils.html import format_html

from .exams import ensure_exam
from .models import Badge, Course, Enrollment, Lesson, LearnerBadge, LessonCompletion, QuizResult, Tier


def _icon_chip(obj):
    return format_html('<span class="c4k-icon"><i class="bi bi-{}"></i></span>', obj.icon)


class CourseInline(admin.TabularInline):
    model = Course
    extra = 0


@admin.register(Tier)
class TierAdmin(admin.ModelAdmin):
    list_display = ("icon_preview", "name", "grade_range", "cbc_alignment", "order")
    list_display_links = ("name",)
    list_editable = ("order",)
    search_fields = ("name", "summary")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [CourseInline]

    @admin.display(description="")
    def icon_preview(self, obj):
        return _icon_chip(obj)


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 0
    prepopulated_fields = {"slug": ("title",)}


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("icon_preview", "title", "tier", "lesson_count", "order")
    list_display_links = ("title",)
    list_editable = ("order",)
    list_filter = ("tier",)
    search_fields = ("title", "summary")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [LessonInline]
    actions = ["rebuild_exam"]

    @admin.action(description="Create / rebuild the module exam from the lesson quizzes")
    def rebuild_exam(self, request, queryset):
        for course in queryset:
            exam, action = ensure_exam(course, refresh=True)
            self.message_user(request, f"{course.title}: exam {action}." if action else f"{course.title}: no quiz questions yet.")

    @admin.display(description="")
    def icon_preview(self, obj):
        return _icon_chip(obj)


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "lesson_type", "duration_minutes", "pass_score_percent", "order")
    list_filter = ("course__tier", "course", "lesson_type")
    search_fields = ("title", "summary", "course__title")
    list_select_related = ("course",)
    prepopulated_fields = {"slug": ("title",)}


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("learner", "course", "progress_percent", "enrolled_at")
    list_filter = ("course__tier", "course")
    search_fields = ("learner__username", "learner__first_name", "learner__last_name")
    list_select_related = ("learner", "course")
    date_hierarchy = "enrolled_at"


@admin.register(LessonCompletion)
class LessonCompletionAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "lesson", "completed_at")
    list_select_related = ("enrollment__learner", "enrollment__course", "lesson")
    date_hierarchy = "completed_at"


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ("icon_preview", "name", "criteria")
    list_display_links = ("name",)
    search_fields = ("name", "description")

    @admin.display(description="")
    def icon_preview(self, obj):
        return _icon_chip(obj)


@admin.register(LearnerBadge)
class LearnerBadgeAdmin(admin.ModelAdmin):
    list_display = ("learner", "badge", "earned_at")
    list_select_related = ("learner", "badge")


@admin.register(QuizResult)
class QuizResultAdmin(admin.ModelAdmin):
    list_display = ("learner", "lesson", "score_percent", "passed", "updated_at")
    list_filter = ("passed", "lesson__course")
    search_fields = ("learner__username", "lesson__title")
    list_select_related = ("learner", "lesson")
