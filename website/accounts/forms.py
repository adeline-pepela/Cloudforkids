from django import forms
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm, UserCreationForm

from core.forms import BootstrapFormMixin

from .models import LearnerProfile, User


class SignUpForm(BootstrapFormMixin, UserCreationForm):
    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=True)
    email = forms.EmailField(required=True)
    role = forms.ChoiceField(
        choices=[c for c in User.Role.choices if c[0] != User.Role.ADMIN], initial=User.Role.LEARNER
    )
    date_of_birth = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}), label="Date of birth")
    parent_name = forms.CharField(required=False, max_length=150, label="Parent or guardian's name")
    parent_email = forms.EmailField(required=False, label="Parent or guardian's email")
    accept_terms = forms.BooleanField(required=True, error_messages={"required": "Please accept the Terms and Privacy Policy to continue."})
    needs_consent = False

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("role") == User.Role.LEARNER:
            born = cleaned.get("date_of_birth")
            if not born:
                self.add_error("date_of_birth", "Please enter your date of birth.")
            elif born > date.today() or not MIN_AGE <= age_on(born) <= MAX_AGE:
                self.add_error("date_of_birth", f"Cloud for Kids learners are {MIN_AGE} to {MAX_AGE} years old. Parents, teachers and others can sign up with the matching role.")
            elif age_on(born) < CONSENT_AGE:
                self.needs_consent = True
                if not cleaned.get("parent_email"):
                    self.add_error("parent_email", "We need a parent or guardian's email to ask their permission.")
                if not cleaned.get("parent_name"):
                    self.add_error("parent_name", "Please enter your parent or guardian's name.")
        return cleaned

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "role", "phone_number", "password1", "password2"]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.role = self.cleaned_data["role"]
        user.terms_accepted_at = timezone.now()
        if user.role == User.Role.FACILITATOR:
            user.is_approved = False  # an admin approves new facilitators
        if user.role == User.Role.LEARNER and self.needs_consent:
            user.is_active = False  # locked until a parent approves
        if commit:
            user.save()
            if user.role == User.Role.LEARNER:
                profile, _ = LearnerProfile.objects.get_or_create(user=user)
                profile.date_of_birth = self.cleaned_data.get("date_of_birth")
                from courses.tiers import suggested_tier

                profile.tier = suggested_tier(profile)  # a starting point; the learner can change it in My Profile
                if self.cleaned_data.get("parent_email"):
                    profile.parent_guardian_email = self.cleaned_data["parent_email"]
                    profile.parent_guardian_name = self.cleaned_data.get("parent_name", "")
                profile.save()
                if self.needs_consent:
                    ParentalConsent.objects.create(
                        user=user, parent_name=self.cleaned_data["parent_name"], parent_email=self.cleaned_data["parent_email"]
                    )
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


class ResetRequestForm(BootstrapFormMixin, PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs.update({"placeholder": "you@example.com", "autocomplete": "email", "autofocus": True})


class NewPasswordForm(BootstrapFormMixin, SetPasswordForm):
    pass

from datetime import date

from django.contrib.auth.forms import AuthenticationForm
from django.utils import timezone

from .models import ParentalConsent

MIN_AGE, MAX_AGE, CONSENT_AGE = 7, 17, 13


def age_on(born, today=None):
    today = today or date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


class ConsentAwareLoginForm(AuthenticationForm):
    """Same as the normal login, but tells a child whose parent has not approved yet what is going on."""

    def clean(self):
        try:
            return super().clean()
        except forms.ValidationError:
            username = self.cleaned_data.get("username", "")
            password = self.cleaned_data.get("password", "")
            user = User.objects.filter(username__iexact=username, is_active=False).first()
            if user and user.check_password(password) and hasattr(user, "consent") and user.consent.status == ParentalConsent.Status.PENDING:
                raise forms.ValidationError(
                    "Your account is waiting for a parent or guardian to approve it. Ask them to open the email we sent.",
                    code="consent_pending",
                )
            raise
