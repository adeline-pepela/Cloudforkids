from datetime import date, timedelta

from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from .models import Assignment, ClassMembership, Classroom, LearnerProfile, ParentalConsent, ParentLink, User

PASSWORD = "Zq9!tr-Kenya42"


def born(years):
    today = date.today()
    return today.replace(year=today.year - years, day=min(today.day, 28))


def signup_data(**extra):
    data = {
        "username": "newbie", "first_name": "New", "last_name": "Bie", "email": "newbie@example.com", "role": "learner",
        "password1": PASSWORD, "password2": PASSWORD, "accept_terms": "on", "date_of_birth": born(15).isoformat(),
    }
    data.update(extra)
    return data


def make(username, role="learner", **extra):
    return User.objects.create_user(username, email=f"{username}@example.com", password=PASSWORD, role=role, first_name=username.title(), **extra)


class SignupTests(TestCase):
    def test_teen_learner_signs_up_and_is_logged_in(self):
        response = self.client.post(reverse("accounts:signup"), signup_data())
        self.assertRedirects(response, reverse("dashboard:home"), fetch_redirect_response=False)
        user = User.objects.get(username="newbie")
        self.assertTrue(user.is_active)
        self.assertIsNotNone(user.terms_accepted_at)
        self.assertEqual(user.learner_profile.date_of_birth, born(15))
        self.assertFalse(hasattr(user, "consent"))
        self.assertEqual(len(mail.outbox), 1)  # welcome email

    def test_terms_must_be_accepted(self):
        data = signup_data()
        del data["accept_terms"]
        self.client.post(reverse("accounts:signup"), data)
        self.assertFalse(User.objects.filter(username="newbie").exists())

    def test_age_limits(self):
        for years in (5, 8, 25):
            response = self.client.post(reverse("accounts:signup"), signup_data(date_of_birth=born(years).isoformat()))
            self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="newbie").exists())

    def test_learner_needs_date_of_birth(self):
        self.client.post(reverse("accounts:signup"), signup_data(date_of_birth=""))
        self.assertFalse(User.objects.filter(username="newbie").exists())

    def test_parent_and_teacher_do_not_need_birth_date(self):
        self.client.post(reverse("accounts:signup"), signup_data(username="mum", role="parent", date_of_birth="", email="mum@example.com"))
        self.assertTrue(User.objects.filter(username="mum", role="parent", is_active=True).exists())

    def test_admin_role_cannot_be_chosen_at_signup(self):
        self.client.post(reverse("accounts:signup"), signup_data(role="admin"))
        self.assertFalse(User.objects.filter(role="admin").exists())


class ParentalConsentTests(TestCase):
    def under13(self, **extra):
        data = signup_data(date_of_birth=born(9).isoformat(), parent_name="Mama Kid", parent_email="mama@example.com")
        data.update(extra)
        return self.client.post(reverse("accounts:signup"), data)

    def test_child_under_13_is_locked_and_parent_is_emailed(self):
        response = self.under13()
        self.assertRedirects(response, reverse("accounts:consent_pending"))
        child = User.objects.get(username="newbie")
        self.assertFalse(child.is_active)
        self.assertEqual(child.consent.status, ParentalConsent.Status.PENDING)
        self.assertEqual([m.to for m in mail.outbox], [["mama@example.com"]])
        self.assertIn(child.consent.token, mail.outbox[0].body)

    def test_parent_details_required_under_13(self):
        response = self.client.post(reverse("accounts:signup"), signup_data(date_of_birth=born(9).isoformat()))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="newbie").exists())

    def test_locked_child_cannot_log_in_and_sees_why(self):
        self.under13()
        response = self.client.post(reverse("accounts:login"), {"username": "newbie", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "waiting for a parent")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_wrong_password_does_not_reveal_pending_account(self):
        self.under13()
        response = self.client.post(reverse("accounts:login"), {"username": "newbie", "password": "wrong"})
        self.assertNotContains(response, "waiting for a parent")

    def test_parent_approves_and_child_can_log_in(self):
        self.under13()
        consent = ParentalConsent.objects.get()
        page = self.client.get(reverse("accounts:consent", args=[consent.token]))
        self.assertContains(page, "I approve")
        self.client.post(reverse("accounts:consent", args=[consent.token]), {"decision": "approve"})
        consent.refresh_from_db()
        self.assertEqual(consent.status, ParentalConsent.Status.APPROVED)
        self.assertIsNotNone(consent.decided_at)
        self.client.logout()
        self.assertTrue(self.client.login(username="newbie", password=PASSWORD))
        self.assertTrue(any("can now use" in m.subject for m in mail.outbox))

    def test_parent_declines_and_account_is_deleted(self):
        self.under13()
        consent = ParentalConsent.objects.get()
        self.client.post(reverse("accounts:consent", args=[consent.token]), {"decision": "decline"})
        self.assertFalse(User.objects.filter(username="newbie").exists())
        self.assertFalse(ParentalConsent.objects.exists())

    def test_bad_token_is_404(self):
        self.assertEqual(self.client.get(reverse("accounts:consent", args=["nope"])).status_code, 404)

    def test_answered_request_cannot_be_changed(self):
        self.under13()
        consent = ParentalConsent.objects.get()
        self.client.post(reverse("accounts:consent", args=[consent.token]), {"decision": "approve"})
        self.client.post(reverse("accounts:consent", args=[consent.token]), {"decision": "decline"})
        self.assertTrue(User.objects.filter(username="newbie").exists())

    def test_resend_is_limited(self):
        cache.clear()
        self.under13()
        sent_before = len(mail.outbox)
        for _ in range(5):
            self.client.post(reverse("accounts:consent_pending"))
        self.assertEqual(len(mail.outbox) - sent_before, 3)


class FacilitatorApprovalTests(TestCase):
    def test_new_facilitator_waits_for_approval(self):
        self.client.post(reverse("accounts:signup"), signup_data(username="teach", role="facilitator", date_of_birth="", email="teach@example.com"))
        teacher = User.objects.get(username="teach")
        self.assertFalse(teacher.is_approved)
        response = self.client.get(reverse("teach:home"))
        self.assertContains(response, "waiting for approval")
        response = self.client.post(reverse("teach:class_new"), {"name": "Club"})
        self.assertEqual(Classroom.objects.count(), 0)
        self.assertContains(response, "waiting for approval")

    def test_admin_approval_unlocks_and_emails(self):
        teacher = make("teach", "facilitator", is_approved=False)
        admin = User.objects.create_superuser("boss", "boss@example.com", PASSWORD, role="admin")
        self.client.force_login(admin)
        self.client.post(reverse("admin:accounts_user_changelist"), {"action": "approve_facilitators", "_selected_action": [teacher.pk]})
        teacher.refresh_from_db()
        self.assertTrue(teacher.is_approved)
        self.assertTrue(any("approved" in m.subject for m in mail.outbox))
        self.client.force_login(teacher)
        self.assertEqual(self.client.get(reverse("teach:home")).status_code, 200)

    def test_admin_add_user_page_asks_for_role(self):
        admin = User.objects.create_superuser("boss", "boss@example.com", PASSWORD, role="admin")
        self.client.force_login(admin)
        page = self.client.get(reverse("admin:accounts_user_add"))
        self.assertContains(page, 'name="role"')
        self.client.post(reverse("admin:accounts_user_add"), {
            "username": "madeit", "first_name": "M", "last_name": "I", "email": "m@example.com", "role": "facilitator",
            "phone_number": "", "password1": PASSWORD, "password2": PASSWORD,
        })
        self.assertEqual(User.objects.get(username="madeit").role, "facilitator")


class RoleRoutingTests(TestCase):
    def test_each_role_lands_in_its_own_area(self):
        for role, name, target in (("parent", "p1", "family:home"), ("facilitator", "t1", "teach:home")):
            self.client.force_login(make(name, role))
            self.assertRedirects(self.client.get(reverse("dashboard:home")), reverse(target), fetch_redirect_response=False)
            self.assertRedirects(self.client.get(reverse("accounts:profile")), reverse(target), fetch_redirect_response=False)
        self.client.force_login(make("l1"))
        self.assertEqual(self.client.get(reverse("dashboard:home")).status_code, 200)

    def test_areas_are_closed_to_other_roles(self):
        learner = make("kid")
        self.client.force_login(learner)
        self.assertRedirects(self.client.get(reverse("family:home")), reverse("dashboard:home"), fetch_redirect_response=False)
        self.assertRedirects(self.client.get(reverse("teach:home")), reverse("dashboard:home"), fetch_redirect_response=False)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("family:home")).status_code, 302)  # to login

    def test_learner_profile_created_automatically(self):
        self.assertTrue(LearnerProfile.objects.filter(user=make("auto")).exists())


class ParentLinkTests(TestCase):
    def setUp(self):
        cache.clear()
        self.kid, self.mum = make("kid"), make("mum", "parent")
        self.code = self.kid.learner_profile.family_code

    def link(self, username="kid", code=None):
        self.client.force_login(self.mum)
        return self.client.post(reverse("family:add"), {"username": username, "code": code or self.code})

    def test_family_code_looks_right(self):
        self.assertEqual(len(self.code), 6)
        self.assertNotIn("0", self.code)

    def test_link_with_correct_code(self):
        self.link()
        self.assertTrue(ParentLink.objects.filter(parent=self.mum, child=self.kid).exists())

    def test_wrong_code_and_wrong_username_are_refused(self):
        self.link(code="AAAAAA")
        self.link(username="nobody")
        self.assertFalse(ParentLink.objects.exists())

    def test_code_is_case_insensitive(self):
        self.link(code=self.code.lower())
        self.assertTrue(ParentLink.objects.exists())

    def test_guessing_is_rate_limited(self):
        cache.clear()
        for _ in range(8):
            self.link(code="AAAAAA")
        self.link()  # even the right code is refused now
        self.assertFalse(ParentLink.objects.exists())

    def test_parent_only_sees_linked_children(self):
        other = make("other")
        self.link()
        self.assertEqual(self.client.get(reverse("family:child", args=[self.kid.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("family:child", args=[other.pk])).status_code, 404)

    def test_remove_link(self):
        self.link()
        self.client.post(reverse("family:remove", args=[self.kid.pk]))
        self.assertFalse(ParentLink.objects.exists())


class ClassroomTests(TestCase):
    def setUp(self):
        self.teacher = make("teach", "facilitator")
        self.classroom = Classroom.objects.create(facilitator=self.teacher, name="Club")
        self.kid = make("kid")

    def test_join_code_is_unique_and_short(self):
        other = Classroom.objects.create(facilitator=self.teacher, name="Another")
        self.assertEqual(len(self.classroom.join_code), 6)
        self.assertNotEqual(self.classroom.join_code, other.join_code)

    def test_learner_joins_with_code(self):
        self.client.force_login(self.kid)
        self.client.post(reverse("accounts:join_class"), {"code": self.classroom.join_code.lower()})
        self.assertTrue(ClassMembership.objects.filter(classroom=self.classroom, learner=self.kid).exists())

    def test_bad_or_archived_code_is_refused(self):
        self.client.force_login(self.kid)
        self.client.post(reverse("accounts:join_class"), {"code": "NOPE12"})
        self.classroom.archived = True
        self.classroom.save()
        self.client.post(reverse("accounts:join_class"), {"code": self.classroom.join_code})
        self.assertFalse(ClassMembership.objects.exists())

    def test_only_learners_can_join(self):
        self.client.force_login(make("mum", "parent"))
        self.client.post(reverse("accounts:join_class"), {"code": self.classroom.join_code})
        self.assertFalse(ClassMembership.objects.exists())

    def test_teacher_sees_only_own_classes_and_learners(self):
        ClassMembership.objects.create(classroom=self.classroom, learner=self.kid)
        rival = make("rival", "facilitator")
        self.client.force_login(rival)
        self.assertEqual(self.client.get(reverse("teach:class", args=[self.classroom.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("teach:learner", args=[self.classroom.pk, self.kid.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("teach:class_export", args=[self.classroom.pk])).status_code, 404)
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse("teach:class", args=[self.classroom.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("teach:learner", args=[self.classroom.pk, self.kid.pk])).status_code, 200)

    def test_learner_not_in_class_is_not_visible(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse("teach:learner", args=[self.classroom.pk, self.kid.pk])).status_code, 404)

    def test_assignment_shows_to_learner_and_emails_family(self):
        from courses.models import Course

        ClassMembership.objects.create(classroom=self.classroom, learner=self.kid)
        course = Course.objects.first()
        self.client.force_login(self.teacher)
        self.client.post(reverse("teach:assignment_add", args=[self.classroom.pk]),
                         {"course": course.pk, "due_date": (date.today() + timedelta(days=3)).isoformat(), "note": "Before Friday"})
        self.assertEqual(Assignment.objects.count(), 1)
        self.client.force_login(self.kid)
        self.assertContains(self.client.get(reverse("dashboard:home")), "From your teacher")
        self.assertTrue(any("New assignment" in m.subject for m in mail.outbox))

    def test_csv_export(self):
        ClassMembership.objects.create(classroom=self.classroom, learner=self.kid)
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("teach:class_export", args=[self.classroom.pk]))
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("Kid", response.content.decode())


class PasswordResetTests(TestCase):
    def test_reset_flow(self):
        user = make("resetme")
        cache.clear()
        response = self.client.post(reverse("accounts:password_reset"), {"email": user.email})
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        link = [w for w in mail.outbox[0].body.split() if "/accounts/reset/" in w][0]
        page = self.client.get(link.replace("http://testserver", ""), follow=True)
        self.assertContains(page, "new_password1")
        self.client.post(page.redirect_chain[-1][0], {"new_password1": "Another-Pass-77!", "new_password2": "Another-Pass-77!"})
        self.assertTrue(self.client.login(username="resetme", password="Another-Pass-77!"))

    def test_unknown_email_gets_same_answer_and_no_mail(self):
        cache.clear()
        response = self.client.post(reverse("accounts:password_reset"), {"email": "ghost@example.com"})
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_requests_are_rate_limited(self):
        user = make("resetme")
        cache.clear()
        for _ in range(8):
            self.client.post(reverse("accounts:password_reset"), {"email": user.email})
        self.assertEqual(len(mail.outbox), 5)


class LegalAndUnsubscribeTests(TestCase):
    def test_terms_and_privacy_pages(self):
        for name in ("core:terms", "core:privacy"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertContains(self.client.get(reverse("core:privacy")), "Data Protection Act")

    def test_unsubscribe_link(self):
        from core import notify

        user = make("mum", "parent")
        token = notify.unsubscribe_url(user).rsplit("/", 2)[-2]
        self.client.post(reverse("accounts:unsubscribe", args=[token]))
        user.refresh_from_db()
        self.assertFalse(user.email_notifications)
        self.assertEqual(self.client.get(reverse("accounts:unsubscribe", args=["garbage"])).status_code, 404)


class ClassScheduleTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("tr", password="pw-12345-Zq", role="facilitator")
        self.kid = User.objects.create_user("pupil", password="pw-12345-Zq", role="learner")
        self.other = User.objects.create_user("outsider", password="pw-12345-Zq", role="learner")
        self.classroom = Classroom.objects.create(facilitator=self.teacher, name="Cloud Club", location="Lab 2", meeting_link="https://meet.example.com/club")

    def add_session(self, **extra):
        from datetime import date, timedelta

        self.client.force_login(self.teacher)
        data = {"date": (date.today() + timedelta(days=3)).isoformat(), "time": "14:30", "duration_minutes": 60, "repeat_weeks": 3, "title": "Storage"}
        data.update(extra)
        return self.client.post(reverse("teach:session_add", args=[self.classroom.pk]), data)

    def test_teacher_adds_a_weekly_run_of_sessions(self):
        from .models import ClassSession

        self.assertRedirects(self.add_session(), reverse("teach:class", args=[self.classroom.pk]))
        sessions = list(ClassSession.objects.filter(classroom=self.classroom))
        self.assertEqual(len(sessions), 3)
        self.assertEqual(sessions[1].starts_at - sessions[0].starts_at, __import__("datetime").timedelta(weeks=1))
        self.assertEqual(sessions[0].where, "Lab 2")  # falls back to the class venue
        self.assertEqual(sessions[0].link, "https://meet.example.com/club")

    def test_past_date_is_refused(self):
        from .models import ClassSession

        self.add_session(date="2020-01-01")
        self.assertFalse(ClassSession.objects.exists())

    def test_only_the_owner_can_schedule(self):
        from .models import ClassSession

        rival = User.objects.create_user("rival", password="pw-12345-Zq", role="facilitator")
        self.client.force_login(rival)
        response = self.client.post(reverse("teach:session_add", args=[self.classroom.pk]), {"date": "2099-01-01", "time": "10:00", "duration_minutes": 60, "repeat_weeks": 1})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(ClassSession.objects.exists())

    def test_joining_shows_the_schedule_to_the_learner_only(self):
        self.add_session()
        self.client.force_login(self.kid)
        joined = self.client.post(reverse("accounts:join_class"), {"code": self.classroom.join_code})
        self.assertRedirects(joined, reverse("dashboard:classes"))
        page = self.client.get(reverse("dashboard:classes"))
        for text in ("Cloud Club", "Lab 2", "Storage", "14:30", "https://meet.example.com/club", "Message teacher"):
            self.assertContains(page, text)
        self.assertContains(self.client.get(reverse("dashboard:home")), "Coming up in my classes")
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse("dashboard:classes")), "Storage")

    def test_calendar_month_navigation_and_due_dates(self):
        from datetime import date, timedelta

        from courses.models import Course

        ClassMembership.objects.create(classroom=self.classroom, learner=self.kid)
        due = date.today() + timedelta(days=2)
        Assignment.objects.create(classroom=self.classroom, course=Course.objects.first(), due_date=due)
        self.client.force_login(self.kid)
        page = self.client.get(reverse("dashboard:classes") + f"?m={due:%Y-%m}")
        self.assertContains(page, "Due: ")
        self.assertEqual(self.client.get(reverse("dashboard:classes") + "?m=garbage").status_code, 200)
