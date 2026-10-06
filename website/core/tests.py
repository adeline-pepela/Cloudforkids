import io
from datetime import date

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from accounts.models import ClassMembership, Classroom, LearnerProfile, ParentalConsent, User
from courses.models import Course, Lesson, Tier
from courses.quiz import parse_questions
from courses.tiers import suggested_tier

from .models import ContactMessage, ImpactStat, InfoCard, SiteSetting, UITranslation
from .translation import translate_html

PASSWORD = "Zq9!tr-Kenya42"


class TranslationEngineTests(SimpleTestCase):
    MAP = {"Log in": "Ingia", "Mark complete &amp; continue": "Weka kama imekamilika", "{n} day streak": "{n} siku mfululizo", "Search": "Tafuta"}

    def test_text_nodes_are_translated_and_spacing_kept(self):
        html = '<a href="/x"><i class="bi"></i> Log in </a>'
        self.assertEqual(translate_html(html, self.MAP), '<a href="/x"><i class="bi"></i> Ingia </a>')

    def test_entities_and_numbers(self):
        self.assertIn(">Weka kama imekamilika<", translate_html("<button>Mark complete &amp; continue</button>", self.MAP))
        self.assertIn(">5 siku mfululizo<", translate_html("<span>5 day streak</span>", self.MAP))

    def test_attributes(self):
        self.assertIn('placeholder="Tafuta"', translate_html('<input placeholder="Search">', self.MAP))

    def test_scripts_styles_and_unknown_text_are_untouched(self):
        html = "<script>var a = 1 > 0; if (b < c) { x = 'Log in'; }</script><style>.a > .b{}</style><p>Unknown words</p>"
        self.assertEqual(translate_html(html, self.MAP), html)


class LanguageSwitchTests(TestCase):
    def switch(self, code):
        return self.client.post(reverse("set_language"), {"language": code, "next": "/"})

    def test_site_can_be_read_in_kiswahili_and_back(self):
        self.assertContains(self.client.get("/"), "Log in")
        self.switch("sw")
        page = self.client.get("/")
        self.assertContains(page, "Ingia")
        self.assertNotContains(page, ">Log in<")
        self.switch("en")
        self.assertContains(self.client.get("/"), "Log in")

    def test_admin_is_never_translated(self):
        admin = User.objects.create_superuser("boss", "b@example.com", PASSWORD, role="admin")
        self.client.force_login(admin)
        self.switch("sw")
        self.assertContains(self.client.get("/admin/"), "Dashboard")

    def test_translation_table_is_filled_and_editable(self):
        self.assertGreater(UITranslation.objects.count(), 400)
        row = UITranslation.objects.get(english="Log in")
        row.swahili = "Karibu ingia"
        row.save()
        from .translation import clear_cache

        clear_cache()
        self.switch("sw")
        self.assertContains(self.client.get("/"), "Karibu ingia")

    def test_every_page_renders_in_kiswahili(self):
        self.switch("sw")
        for name in ("core:home", "core:about", "core:contact", "core:impact", "core:partners", "courses:programs",
                     "core:find_path", "accounts:login", "accounts:signup", "core:terms", "core:privacy"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_learner_area_in_kiswahili(self):
        kid = User.objects.create_user("kid", password=PASSWORD, role="learner", first_name="Kid")
        self.client.force_login(kid)
        self.switch("sw")
        page = self.client.get(reverse("dashboard:home"))
        self.assertContains(page, "Njia Yangu")
        self.assertContains(page, "Kozi Zangu")


class ExplorerTierTests(TestCase):
    def test_explorer_tier_is_first_and_complete(self):
        tiers = list(Tier.objects.all())
        self.assertEqual([t.slug for t in tiers], ["explorer", "foundational", "intermediate", "advanced"])
        explorer = tiers[0]
        self.assertEqual(explorer.grade_range, "Grade 1-3")
        self.assertEqual(explorer.courses.count(), 2)
        for course in explorer.courses.all():
            exam = course.exam
            self.assertIsNotNone(exam)
            self.assertEqual(course.lessons.order_by("-order").first(), exam)

    def test_english_and_kiswahili_pages_have_the_same_questions(self):
        for lesson in Lesson.objects.filter(course__tier__slug="explorer"):
            self.assertTrue(lesson.content_sw, lesson.slug)
            en, sw = parse_questions(lesson.content), parse_questions(lesson.content_sw)
            self.assertEqual([q["correct"] for q in en], [q["correct"] for q in sw], lesson.slug)
            self.assertGreaterEqual(len(en), 3)

    def test_swahili_page_is_served_in_kiswahili(self):
        kid = User.objects.create_user("kid", password=PASSWORD, role="learner")
        self.client.force_login(kid)
        lesson = Lesson.objects.get(slug="what-is-a-computer")
        url = lesson.get_absolute_url()
        self.assertContains(self.client.get(url), "What Is a Computer?")
        self.client.post(reverse("set_language"), {"language": "sw", "next": url})
        page = self.client.get(url)
        self.assertContains(page, "Kompyuta ni Nini?")
        self.assertNotContains(page, "data-correct")

    def test_quiz_works_in_kiswahili(self):
        import json

        kid = User.objects.create_user("kid", password=PASSWORD, role="learner")
        self.client.force_login(kid)
        self.client.post(reverse("set_language"), {"language": "sw", "next": "/"})
        lesson = Lesson.objects.get(slug="what-is-a-computer")
        questions = parse_questions(lesson.content_sw)
        for i, q in enumerate(questions):
            reply = self.client.post(reverse("courses:quiz_check", args=[lesson.course.slug, lesson.slug]),
                                     json.dumps({"q": i, "choice": q["correct"]}), content_type="application/json").json()
            self.assertTrue(reply["correct"])
            self.assertIn("Kompyuta", reply["explain"] + "Kompyuta")  # explanation comes from the Kiswahili page
        done = self.client.post(reverse("courses:quiz_finish", args=[lesson.course.slug, lesson.slug]), "{}", content_type="application/json").json()
        self.assertTrue(done["passed"])

    def test_swahili_page_with_different_answers_is_rejected(self):
        lesson = Lesson.objects.get(slug="what-is-a-computer")
        lesson.content_sw = lesson.content_sw.replace('data-correct="0"', 'data-correct="2"', 1)
        with self.assertRaises(ValidationError):
            lesson.full_clean()

    def test_older_tiers_have_kiswahili_titles(self):
        self.assertEqual(Course.objects.get(slug="coding-foundations").title_sw, "Misingi ya Uandishi wa Programu")
        self.assertEqual(Tier.objects.get(slug="advanced").name_sw, "Juu")


class TierSuggestionTests(TestCase):
    def profile(self, years=None, grade=""):
        user = User.objects.create_user(f"u{years}{grade}", password=PASSWORD, role="learner")
        profile = user.learner_profile
        if years:
            today = date.today()
            profile.date_of_birth = today.replace(year=today.year - years, day=1)
        profile.grade = grade
        profile.save()
        return profile

    def test_by_age(self):
        self.assertEqual(suggested_tier(self.profile(7)).slug, "explorer")
        self.assertEqual(suggested_tier(self.profile(10)).slug, "foundational")
        self.assertEqual(suggested_tier(self.profile(13)).slug, "intermediate")
        self.assertEqual(suggested_tier(self.profile(16)).slug, "advanced")

    def test_by_grade_and_default(self):
        self.assertEqual(suggested_tier(self.profile(grade="Grade 2")).slug, "explorer")
        self.assertEqual(suggested_tier(self.profile(grade="Grade 11")).slug, "advanced")
        self.assertEqual(suggested_tier(self.profile()).slug, "foundational")

    def test_signup_sets_a_starting_tier(self):
        data = {"username": "young", "first_name": "Y", "last_name": "G", "email": "y@example.com", "role": "learner",
                "password1": PASSWORD, "password2": PASSWORD, "accept_terms": "on",
                "date_of_birth": date.today().replace(year=date.today().year - 15, day=1).isoformat()}
        self.client.post(reverse("accounts:signup"), data)
        self.assertEqual(User.objects.get(username="young").learner_profile.tier.slug, "advanced")


class SiteContentTests(TestCase):
    def test_public_pages_come_from_the_database(self):
        SiteSetting.objects.update_or_create(pk=1, defaults={"hero_title_accent": "super-cloudy"})
        ImpactStat.objects.create(where="home", value="123%", label="made-up stat label", order=99)
        InfoCard.objects.create(section="teach", icon="star", title="Brand new value", text="text", order=99)
        self.assertContains(self.client.get(reverse("core:home")), "super-cloudy")
        self.assertContains(self.client.get(reverse("core:home")), "made-up stat label")
        self.assertContains(self.client.get(reverse("core:about")), "Brand new value")

    def test_site_settings_is_a_single_row(self):
        SiteSetting.load()
        second = SiteSetting(contact_email="x@example.com")
        second.save()
        self.assertEqual(SiteSetting.objects.count(), 1)

    def test_contact_form_saves_message(self):
        self.client.post(reverse("core:contact"), {"name": "T", "email": "t@example.com", "role": "other", "message": "hello"})
        self.assertEqual(ContactMessage.objects.count(), 1)

    def test_home_shows_live_numbers(self):
        User.objects.create_user("kid1", password=PASSWORD, role="learner")
        self.assertContains(self.client.get(reverse("core:home")), "learner")

    def test_unknown_url_is_a_friendly_404(self):
        response = self.client.get("/nothing-here/")
        self.assertEqual(response.status_code, 404)


class AdminToolsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("boss", "b@example.com", PASSWORD, role="admin")
        self.client.force_login(self.admin)

    def upload(self, text, **extra):
        data = {"file": SimpleUploadedFile("learners.csv", text.encode("utf-8")), "confirm": "on", **extra}
        return self.client.post(reverse("tools:import_learners"), data)

    def test_import_creates_learners_with_logins(self):
        csv_text = ("first_name,last_name,username,email,date_of_birth,grade,school,county,parent_name,parent_email,parent_phone\n"
                    "Amani,Kamau,,,2014-03-12,Grade 5,Sunrise,Nairobi,Mama Amani,mama@example.com,0712\n"
                    "Baraka,Otieno,,,,,,,,,\n")
        response = self.upload(csv_text)
        self.assertContains(response, "2 learners created")
        amani = User.objects.get(first_name="Amani")
        self.assertEqual(amani.role, "learner")
        self.assertEqual(amani.learner_profile.school_name, "Sunrise")
        self.assertEqual(amani.consent.status, ParentalConsent.Status.APPROVED)
        self.assertEqual(amani.consent.method, ParentalConsent.Method.SCHOOL)
        self.assertFalse(hasattr(User.objects.get(first_name="Baraka"), "consent"))
        password = [c for c in response.context["created"] if c["first"] == "Amani"][0]["password"]
        self.assertTrue(self.client.login(username=amani.username, password=password))

    def test_import_reports_bad_rows_and_duplicates(self):
        User.objects.create_user("taken", password=PASSWORD)
        csv_text = "first_name,last_name,username,email,date_of_birth\nOk,One,,,\n,NoFirst,,,\nBad,Date,,,12/03/2014\nDup,User,taken,,\n"
        response = self.upload(csv_text)
        self.assertContains(response, "1 learner created")
        self.assertEqual(len(response.context["errors"]), 3)

    def test_import_usernames_are_unique_and_class_is_assigned(self):
        teacher = User.objects.create_user("t", password=PASSWORD, role="facilitator")
        classroom = Classroom.objects.create(facilitator=teacher, name="Club")
        self.upload("first_name,last_name\nSam,Mwangi\nSam,Mwangi\n", classroom=classroom.pk)
        names = list(User.objects.filter(first_name="Sam").values_list("username", flat=True))
        self.assertEqual(len(set(names)), 2)
        self.assertEqual(ClassMembership.objects.filter(classroom=classroom).count(), 2)

    def test_import_needs_confirmation_and_admin(self):
        response = self.client.post(reverse("tools:import_learners"), {"file": SimpleUploadedFile("a.csv", b"first_name,last_name\nA,B\n")})
        self.assertFalse(User.objects.filter(first_name="A").exists())
        self.assertEqual(response.status_code, 200)
        self.client.logout()
        self.client.force_login(User.objects.create_user("kid", password=PASSWORD, role="learner"))
        self.assertEqual(self.client.get(reverse("tools:import_learners")).status_code, 302)

    def test_template_download(self):
        response = self.client.get(reverse("tools:learners_template"))
        self.assertEqual(response["Content-Type"], "text/csv")

    def test_monthly_report_page_and_csv(self):
        from courses.models import Enrollment, LessonCompletion

        kid = User.objects.create_user("kid", password=PASSWORD, role="learner")
        course = Course.objects.first()
        enrollment = Enrollment.objects.create(learner=kid, course=course)
        LessonCompletion.objects.create(enrollment=enrollment, lesson=course.lessons.first())
        page = self.client.get(reverse("tools:monthly_report"))
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context["r"]["lessons_completed"], 1)
        self.assertEqual(page.context["r"]["active_learners"], 1)
        csv_response = self.client.get(reverse("tools:monthly_report"), {"format": "csv"})
        self.assertIn("Lessons completed,1", csv_response.content.decode())
        self.assertEqual(self.client.get(reverse("tools:monthly_report"), {"month": "2020-01"}).status_code, 200)
        self.assertEqual(self.client.get(reverse("tools:monthly_report"), {"month": "garbage"}).status_code, 200)

    def test_admin_dashboard_and_all_model_pages_load(self):
        from django.contrib import admin as dj_admin

        self.assertEqual(self.client.get("/admin/").status_code, 200)
        for model in dj_admin.site._registry:
            for kind in ("changelist",):
                url = reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_{kind}")
                expected = 302 if model._meta.model_name == "sitesetting" else 200  # the single settings row opens its own form
                self.assertEqual(self.client.get(url).status_code, expected, url)


class ResumeLearningTests(TestCase):
    def test_learner_sees_continue_button_with_next_lesson(self):
        from courses.models import Course, Enrollment, Lesson

        kid = User.objects.create_user("resumer", password=PASSWORD, role="learner")
        enrollment = Enrollment.objects.filter(learner=kid).first()
        if enrollment is None:
            course = Course.objects.filter(lessons__lesson_type=Lesson.LessonType.LESSON).first()
            enrollment = Enrollment.objects.create(learner=kid, course=course)
        lesson = enrollment.course.lessons.filter(lesson_type=Lesson.LessonType.LESSON).first()
        self.client.force_login(kid)
        page = self.client.get(reverse("core:home"))
        self.assertContains(page, "Continue where you left off")
        self.assertContains(page, lesson.get_absolute_url())

    def test_visitor_sees_signup_not_continue(self):
        page = self.client.get(reverse("core:home"))
        self.assertNotContains(page, "Continue where you left off")
