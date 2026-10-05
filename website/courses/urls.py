from django.urls import path

from . import views

app_name = "courses"

urlpatterns = [
    path("", views.programs, name="programs"),
    path("<slug:slug>/", views.course_detail, name="course_detail"),
    path("<slug:slug>/enroll/", views.enroll, name="enroll"),
    path("<slug:course_slug>/<slug:lesson_slug>/", views.lesson_detail, name="lesson_detail"),
    path("<slug:course_slug>/<slug:lesson_slug>/quiz-check/", views.quiz_check, name="quiz_check"),
    path("<slug:course_slug>/<slug:lesson_slug>/quiz-finish/", views.quiz_finish, name="quiz_finish"),
    path("<slug:course_slug>/<slug:lesson_slug>/quiz-grade/", views.quiz_grade, name="quiz_grade"),
    path("<slug:course_slug>/<slug:lesson_slug>/quiz-reset/", views.quiz_reset, name="quiz_reset"),
    path(
        "<slug:course_slug>/<slug:lesson_slug>/complete/",
        views.mark_lesson_complete,
        name="mark_lesson_complete",
    ),
]
