from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from core import notify

from .models import Assignment, ClassMembership, Classroom, LearnerProfile, Message, ParentalConsent, ParentLink, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "first_name", "last_name", "email", "role", "is_approved", "is_active", "is_staff")
    list_filter = ("role", "is_approved") + tuple(DjangoUserAdmin.list_filter)
    actions = ["approve_facilitators"]

    @admin.action(description="Approve selected facilitators (and email them)")
    def approve_facilitators(self, request, queryset):
        count = 0
        for user in queryset.filter(role=User.Role.FACILITATOR, is_approved=False):
            user.is_approved = True
            user.save(update_fields=["is_approved"])
            notify.send_teacher_approved(user)
            count += 1
        self.message_user(request, f"{count} facilitator(s) approved.")
    date_hierarchy = "date_joined"
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Cloud for Kids", {"fields": ("role", "is_approved", "phone_number", "email_notifications", "terms_accepted_at")}),
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


@admin.register(ParentalConsent)
class ParentalConsentAdmin(admin.ModelAdmin):
    list_display = ("user", "parent_name", "parent_email", "status", "method", "created_at", "decided_at")
    list_filter = ("status", "method")
    search_fields = ("user__username", "parent_email", "parent_name")
    readonly_fields = ("token", "created_at", "decided_at")
    actions = ["record_consent", "resend_request"]

    @admin.action(description="Record consent (parent confirmed another way) and activate the account")
    def record_consent(self, request, queryset):
        from django.utils import timezone

        for consent in queryset.filter(status=ParentalConsent.Status.PENDING):
            consent.status = ParentalConsent.Status.APPROVED
            consent.method = ParentalConsent.Method.ADMIN
            consent.decided_at = timezone.now()
            consent.save()
            consent.user.is_active = True
            consent.user.save(update_fields=["is_active"])
        self.message_user(request, "Consent recorded.")

    @admin.action(description="Email the parent the approval link again")
    def resend_request(self, request, queryset):
        for consent in queryset.filter(status=ParentalConsent.Status.PENDING):
            notify.send_consent_request(consent)
        self.message_user(request, "Emails queued.")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("subject", "sender", "recipient", "classroom", "created_at", "read_at")
    list_filter = ("classroom",)
    search_fields = ("subject", "body", "sender__username", "recipient__username")
    raw_id_fields = ("sender", "recipient", "about_learner", "reply_to")
