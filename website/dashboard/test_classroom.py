from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from accounts.models import Assignment, ClassMembership, Classroom, ClassPost, User
from courses.models import Course, QuizResult
from courses.quiz import quiz_question_count

PASSWORD = "pw-12345-Zq"


class ClassPagesTests(TestCase):
    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user("mwalimu", password=PASSWORD, role="facilitator", first_name="Grace", last_name="Wanjiru")
        self.kid = User.objects.create_user("amani", password=PASSWORD, role="learner", first_name="Amani", last_name="Otieno")
        self.mate = User.objects.create_user("zawadi", password=PASSWORD, role="learner", first_name="Zawadi", last_name="Kamau")
        self.outsider = User.objects.create_user("baraka", password=PASSWORD, role="learner")
        self.classroom = Classroom.objects.create(facilitator=self.teacher, name="Grade 6 Cloud Club")
        self.other = Classroom.objects.create(facilitator=self.teacher, name="Saturday Coders")
        for kid in (self.kid, self.mate):
            ClassMembership.objects.create(classroom=self.classroom, learner=kid)
        self.url = reverse("dashboard:class", args=[self.classroom.pk])

    def login(self, user):
        self.client.login(username=user.username, password=PASSWORD)

    def post(self, body, parent=None):
        cache.clear()
        data = {"body": body}
        if parent:
            data["parent"] = parent.pk
        return self.client.post(reverse("dashboard:discussion_post", args=[self.classroom.pk]), data)

    def test_teacher_sidebar_has_one_my_classes_link(self):
        self.login(self.teacher)
        page = self.client.get(reverse("teach:home")).content.decode()
        nav = page[page.index('aria-label="Facilitator menu"'):page.index("</nav>", page.index('aria-label="Facilitator menu"'))]
        self.assertIn("My classes", nav)
        self.assertNotIn("Saturday Coders", nav)
        listing = self.client.get(reverse("teach:classes"))
        self.assertContains(listing, "Grade 6 Cloud Club")
        self.assertContains(listing, "Saturday Coders")
        self.assertContains(self.client.get(reverse("teach:class", args=[self.classroom.pk])), 'class="l-link active" href="/teach/classes/"')

    def test_learner_class_page_tabs(self):
        course = Course.objects.filter(lessons__isnull=False).first()
        Assignment.objects.create(classroom=self.classroom, course=course, note="Finish before Friday")
        quiz_lesson = next(l for l in course.lessons.all() if quiz_question_count(l))
        QuizResult.objects.create(learner=self.kid, lesson=quiz_lesson, score_percent=90, passed=True)
        self.login(self.kid)
        self.assertContains(self.client.get(self.url), "Class discussion")
        self.assertContains(self.client.get(self.url + "?tab=assignments"), "Finish before Friday")
        quizzes = self.client.get(self.url + "?tab=quizzes")
        self.assertContains(quizzes, quiz_lesson.title)
        self.assertContains(quizzes, "90%")
        people = self.client.get(self.url + "?tab=people")
        self.assertContains(people, "Zawadi K.")
        self.assertNotContains(people, "Kamau")
        self.assertContains(self.client.get(self.url + "?tab=schedule"), "Nothing scheduled yet")
        self.assertContains(self.client.get(reverse("dashboard:classes")), self.url)

    def test_outsiders_cannot_open_the_class(self):
        self.login(self.outsider)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.post("hi").status_code, 404)

    def test_discussion_post_reply_and_filter(self):
        self.login(self.kid)
        self.post("How do I make an S3 bucket?")
        question = ClassPost.objects.get()
        self.login(self.mate)
        self.post("Use the console!", parent=question)
        response = self.post("text me on 0712345678")
        self.assertFalse(ClassPost.objects.get(body__startswith="text me").parent_id)
        self.assertTrue(ClassPost.objects.get(body__startswith="text me").flagged)
        page = self.client.get(self.url)
        self.assertContains(page, "How do I make an S3 bucket?")
        self.assertContains(page, "Use the console!")
        self.assertContains(page, "Amani O.")
        self.assertNotContains(page, "text me on")
        # The teacher sees the blocked post and can show it, pin and remove posts
        self.login(self.teacher)
        board = self.client.get(reverse("teach:discussion", args=[self.classroom.pk]))
        self.assertContains(board, "text me on")
        self.assertContains(board, "Blocked by the filter (phone)")
        self.client.post(reverse("dashboard:discussion_action", args=[self.classroom.pk, question.pk, "pin"]))
        self.assertTrue(ClassPost.objects.get(pk=question.pk).pinned)
        # A classmate may not remove someone else's post
        self.login(self.mate)
        self.assertEqual(self.client.post(reverse("dashboard:discussion_action", args=[self.classroom.pk, question.pk, "delete"])).status_code, 404)
        self.login(self.kid)
        self.client.post(reverse("dashboard:discussion_action", args=[self.classroom.pk, question.pk, "delete"]))
        self.assertTrue(ClassPost.objects.get(pk=question.pk).hidden)

    def test_discussion_switched_off(self):
        self.classroom.discussion_enabled = False
        self.classroom.save()
        self.login(self.kid)
        self.post("hello")
        self.assertFalse(ClassPost.objects.exists())
        self.assertContains(self.client.get(self.url), "turned the class discussion off")
        self.login(self.teacher)
        self.post("Announcement: class is at 4pm, see https://example.com")
        self.assertFalse(ClassPost.objects.get().flagged)  # teachers may share links
