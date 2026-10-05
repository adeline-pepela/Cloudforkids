from django import forms
from django.contrib.auth.forms import UserCreationForm

from core.forms import BootstrapFormMixin

from .models import LearnerProfile, User


class SignUpForm(BootstrapFormMixin, UserCreationForm):
    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=True)
    email = forms.EmailField(required=True)
    role = forms.ChoiceField(
        choices=[c for c in User.Role.choices if c[0] != User.Role.ADMIN], initial=User.Role.LEARNER
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "role", "phone_number", "password1", "password2"]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.role = self.cleaned_data["role"]
        if commit:
            user.save()
            if user.role == User.Role.LEARNER:
                LearnerProfile.objects.get_or_create(user=user)
        return user


class LearnerProfileForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = LearnerProfile
        fields = [
            "tier",
            "grade",
            "school_name",
            "county",
            "parent_guardian_name",
            "parent_guardian_email",
            "parent_guardian_phone",
            "date_of_birth",
            "bio",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "bio": forms.Textarea(attrs={"rows": 3, "placeholder": "What do you like? What would you like to build?"}),
            "grade": forms.TextInput(attrs={"placeholder": "e.g. Grade 6"}),
            "school_name": forms.TextInput(attrs={"placeholder": "Name of your school"}),
            "county": forms.TextInput(attrs={"placeholder": "e.g. Nairobi"}),
            "parent_guardian_name": forms.TextInput(attrs={"placeholder": "Full name"}),
            "parent_guardian_email": forms.EmailInput(attrs={"placeholder": "parent@example.com"}),
            "parent_guardian_phone": forms.TextInput(attrs={"placeholder": "07xx xxx xxx"}),
        }
