from django.contrib import admin

from .models import Badge, Course, Enrollment, Lesson, LearnerBadge, LessonCompletion, Tier


class CourseInline(admin.TabularInline):
    model = Course
    extra = 0


@admin.register(Tier)
class TierAdmin(admin.ModelAdmin):
    list_display = ("name", "grade_range", "cbc_alignment", "order")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [CourseInline]


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 0
    prepopulated_fields = {"slug": ("title",)}


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("title", "tier", "lesson_count", "order")
    list_filter = ("tier",)
    prepopulated_fields = {"slug": ("title",)}
    inlines = [LessonInline]


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "duration_minutes", "order")
    list_filter = ("course__tier", "course")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("learner", "course", "progress_percent", "enrolled_at")
    list_filter = ("course__tier", "course")
    search_fields = ("learner__username", "learner__first_name", "learner__last_name")


@admin.register(LessonCompletion)
class LessonCompletionAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "lesson", "completed_at")


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ("name", "icon", "criteria")


@admin.register(LearnerBadge)
class LearnerBadgeAdmin(admin.ModelAdmin):
    list_display = ("learner", "badge", "earned_at")
