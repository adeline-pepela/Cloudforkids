import json

from django.test import TestCase
from django.urls import reverse

from accounts.models import User

from .exams import ensure_exam
from .models import Course, Enrollment, Lesson, LessonCompletion, QuizResult
from .quiz import parse_questions, public_html


class QuizServerSideTests(TestCase):
    """Quizzes are graded by the server; the browser never receives the answers."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("quizzer", password="pw-12345-Zq", role="learner")
        cls.course = Course.objects.get(slug="what-is-the-cloud-really")
        cls.lesson = cls.course.lessons.get(slug="data-storage-basics")
        cls.questions = parse_questions(cls.lesson.content)

    def setUp(self):
        self.client.force_login(self.user)

    def url(self, name, lesson=None):
        lesson = lesson or self.lesson
        return reverse(f"courses:{name}", args=[lesson.course.slug, lesson.slug])

    def post(self, name, data=None, lesson=None):
        return self.client.post(self.url(name, lesson), json.dumps(data or {}), content_type="application/json")

    def test_page_has_no_answer_key(self):
        html = self.client.get(self.url("lesson_detail")).content.decode()
        self.assertIn('class="mcq-question"', html)
        self.assertNotIn("data-correct", html)
        self.assertNotIn("mcq-explain", html)

    def test_public_html_strips_answers_but_keeps_questions(self):
        cleaned = public_html(self.lesson.content)
        self.assertEqual(cleaned.count('class="mcq-question"'), len(self.questions))
        self.assertNotIn("data-correct", cleaned)

    def test_options_are_shuffled_but_keep_their_index(self):
        import re

        seen = set()
        for _ in range(12):
            html = self.client.get(self.url("lesson_detail")).content.decode()
            first = re.search(r'<div class="mcq-options">(.*?)</div>', html, re.S).group(1)
            seen.add(tuple(re.findall(r'data-index="(\d)"', first)))
            self.assertEqual(sorted(re.findall(r'data-index="(\d)"', first)), ["0", "1", "2", "3"])
        self.assertGreater(len(seen), 1)  # not always the same order, so the first button is not always right

    def test_check_reports_correct_and_wrong(self):
        right = self.questions[0]["correct"]
        ok = self.post("quiz_check", {"q": 0, "choice": right}).json()
        self.assertTrue(ok["correct"])
        self.assertEqual(ok["correct_index"], right)
        self.assertTrue(ok["explain"])
        wrong = self.post("quiz_check", {"q": 1, "choice": (self.questions[1]["correct"] + 1) % 4}).json()
        self.assertFalse(wrong["correct"])

    def test_first_answer_counts(self):
        right = self.questions[0]["correct"]
        self.post("quiz_check", {"q": 0, "choice": (right + 1) % 4})
        again = self.post("quiz_check", {"q": 0, "choice": right}).json()
        self.assertFalse(again["correct"])  # changing the answer afterwards does not help

    def test_bad_requests_rejected(self):
        self.assertEqual(self.post("quiz_check", {"q": 99, "choice": 0}).status_code, 400)
        self.assertEqual(self.post("quiz_check", {"q": 0}).status_code, 400)
        self.assertEqual(self.post("quiz_grade", {"answers": [0]}).status_code, 400)

    def test_cannot_finish_without_answering(self):
        self.assertEqual(self.post("quiz_finish").status_code, 400)
        self.assertFalse(QuizResult.objects.filter(learner=self.user).exists())

    def test_cannot_complete_without_passing(self):
        self.client.get(self.url("lesson_detail"))
        response = self.client.post(self.url("mark_lesson_complete"))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(LessonCompletion.objects.filter(enrollment__learner=self.user).exists())

    def test_failed_quiz_does_not_unlock(self):
        for i, item in enumerate(self.questions):
            self.post("quiz_check", {"q": i, "choice": (item["correct"] + 1) % 4})
        result = self.post("quiz_finish").json()
        self.assertFalse(result["passed"])
        self.client.post(self.url("mark_lesson_complete"))
        self.assertFalse(LessonCompletion.objects.filter(enrollment__learner=self.user).exists())

    def test_pass_then_complete_stores_score(self):
        for i, item in enumerate(self.questions):
            self.post("quiz_check", {"q": i, "choice": item["correct"]})
        result = self.post("quiz_finish").json()
        self.assertTrue(result["passed"])
        self.assertEqual(result["score_percent"], 100)
        self.client.post(self.url("mark_lesson_complete"))
        completion = LessonCompletion.objects.get(enrollment__learner=self.user, lesson=self.lesson)
        self.assertEqual(completion.score_percent, 100)

    def test_reset_allows_retry_and_keeps_best_score(self):
        for i, item in enumerate(self.questions):
            self.post("quiz_check", {"q": i, "choice": item["correct"]})
        self.post("quiz_finish")
        self.post("quiz_reset")
        for i, item in enumerate(self.questions):
            self.post("quiz_check", {"q": i, "choice": (item["correct"] + 1) % 4})
        self.post("quiz_finish")
        result = QuizResult.objects.get(learner=self.user, lesson=self.lesson)
        self.assertEqual(result.score_percent, 100)
        self.assertTrue(result.passed)

    def test_exam_is_graded_on_the_server(self):
        exam = self.course.exam
        questions = parse_questions(exam.content)
        wrong = [(q["correct"] + 1) % 4 for q in questions]
        failed = self.post("quiz_grade", {"answers": wrong}, lesson=exam).json()
        self.assertFalse(failed["passed"])
        self.assertEqual(len(failed["results"]), len(questions))
        passed = self.post("quiz_grade", {"answers": [q["correct"] for q in questions]}, lesson=exam).json()
        self.assertTrue(passed["passed"])
        self.assertTrue(QuizResult.objects.get(learner=self.user, lesson=exam).passed)

    def test_anonymous_cannot_post_answers(self):
        self.client.logout()
        response = self.post("quiz_check", {"q": 0, "choice": 0})
        self.assertEqual(response.status_code, 302)


class CourseStructureTests(TestCase):
    def test_programme_shape(self):
        self.assertEqual(Course.objects.filter(lessons__lesson_type="exam").distinct().count(), Course.objects.count())
        for course in Course.objects.all():
            self.assertEqual(course.lessons.filter(lesson_type="exam").count(), 1, course.title)

    def test_exam_is_last_and_passes_at_70(self):
        for course in Course.objects.all():
            last = course.lessons.order_by("-order").first()
            self.assertTrue(last.is_exam, course.title)
            self.assertEqual(last.pass_score_percent, 70)

    def test_saving_a_lesson_creates_missing_exam(self):
        tier = Course.objects.first().tier
        course = Course.objects.create(tier=tier, title="Temp", slug="temp", summary="x")
        question = '<div class="mcq-question" data-correct="0"><p>q</p><div class="mcq-options"></div><div class="mcq-explain">e</div></div>'
        Lesson.objects.create(course=course, title="L", slug="l", content=question, order=0)
        exam = course.lessons.get(lesson_type="exam")
        self.assertEqual(exam.order, 1)
        self.assertEqual(len(parse_questions(exam.content)), 1)

    def test_course_complete_only_when_exam_passed(self):
        user = User.objects.create_user("grad", password="pw-12345-Zq", role="learner")
        course = Course.objects.get(slug="my-first-digital-projects")
        enrollment = Enrollment.objects.create(learner=user, course=course)
        for lesson in course.lessons.exclude(lesson_type="exam"):
            LessonCompletion.objects.create(enrollment=enrollment, lesson=lesson)
        self.assertFalse(enrollment.is_complete)
        LessonCompletion.objects.create(enrollment=enrollment, lesson=course.exam)
        self.assertTrue(enrollment.is_complete)

    def test_ensure_exam_refresh(self):
        course = Course.objects.get(slug="coding-foundations")
        exam, action = ensure_exam(course, refresh=True)
        self.assertEqual(action, "refreshed")
        self.assertTrue(parse_questions(exam.content))


class DemoStudentsTests(TestCase):
    def test_seed_and_clear_demo_students(self):
        from django.core.management import call_command

        from accounts.models import User
        from courses.models import LearnerBadge

        call_command("seed_demo_students", count=15, verbosity=0)
        demo = User.objects.filter(email__endswith="@demo.cloudforkids.local")
        self.assertEqual(demo.count(), 15)
        self.assertGreater(len({u.learner_profile.tier_id for u in demo}), 1)  # different pathways
        self.assertTrue(LearnerBadge.objects.filter(learner__in=demo).exists())  # some have badges
        call_command("seed_demo_students", count=15, verbosity=0)  # re-running adds nothing
        self.assertEqual(demo.count(), 15)
        call_command("seed_demo_students", clear=True, verbosity=0)
        self.assertEqual(User.objects.filter(email__endswith="@demo.cloudforkids.local").count(), 0)
