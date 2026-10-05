from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Assignment, ClassMembership, Classroom, LearnerProfile, ParentLink, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "first_name", "last_name", "email", "role", "is_staff")
    list_filter = ("role",) + tuple(DjangoUserAdmin.list_filter)
    date_hierarchy = "date_joined"
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Cloud for Kids", {"fields": ("role", "phone_number")}),
    )
    # The "Add user" page: pick the role (learner, parent, facilitator or admin) as the account is created.
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "first_name", "last_name", "email", "role", "phone_number", "password1", "password2"),
        }),
    )


@admin.register(LearnerProfile)
class LearnerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "tier", "grade", "school_name", "county")
    list_filter = ("tier", "county")
    search_fields = ("user__username", "user__first_name", "user__last_name", "school_name")


class MembershipInline(admin.TabularInline):
    model = ClassMembership
    extra = 0
    autocomplete_fields = ()
    raw_id_fields = ("learner",)


class AssignmentInline(admin.TabularInline):
    model = Assignment
    extra = 0


@admin.register(Classroom)
class ClassroomAdmin(admin.ModelAdmin):
    list_display = ("name", "facilitator", "tier", "school_name", "join_code", "member_count", "archived")
    list_filter = ("tier", "archived")
    search_fields = ("name", "school_name", "facilitator__username", "join_code")
    readonly_fields = ("join_code",)
    inlines = [MembershipInline, AssignmentInline]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "facilitator":
            kwargs["queryset"] = User.objects.filter(role=User.Role.FACILITATOR)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description="Learners")
    def member_count(self, obj):
        return obj.memberships.count()


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("course", "classroom", "due_date", "created_at")
    list_filter = ("classroom",)


@admin.register(ParentLink)
class ParentLinkAdmin(admin.ModelAdmin):
    list_display = ("parent", "child", "created_at")
    search_fields = ("parent__username", "child__username")
    raw_id_fields = ("parent", "child")
