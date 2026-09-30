from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import LearnerProfile, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "first_name", "last_name", "email", "role", "is_staff")
    list_filter = DjangoUserAdmin.list_filter + ("role",)
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Cloud for Kids", {"fields": ("role", "phone_number")}),
    )


@admin.register(LearnerProfile)
class LearnerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "tier", "grade", "school_name", "county")
    list_filter = ("tier", "county")
    search_fields = ("user__username", "user__first_name", "user__last_name", "school_name")
