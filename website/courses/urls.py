from django.urls import path

from . import views

app_name = "courses"

urlpatterns = [
    path("", views.programs, name="programs"),
    path("<slug:slug>/", views.course_detail, name="course_detail"),
    path("<slug:slug>/enroll/", views.enroll, name="enroll"),
    path("<slug:course_slug>/<slug:lesson_slug>/", views.lesson_detail, name="lesson_detail"),
    path(
        "<slug:course_slug>/<slug:lesson_slug>/quiz-result/",
        views.quiz_result,
        name="quiz_result",
    ),
    path(
        "<slug:course_slug>/<slug:lesson_slug>/complete/",
        views.mark_lesson_complete,
        name="mark_lesson_complete",
    ),
]
