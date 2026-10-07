from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("path/", views.path, name="path"),
    path("courses/", views.my_courses, name="courses"),
    path("classes/", views.my_classes, name="classes"),
    path("achievements/", views.achievements, name="achievements"),
    path("labs/", views.labs, name="labs"),
    path("labs/<slug:slug>/", views.lab, name="lab"),
    path("labs/<slug:slug>/complete/", views.lab_complete, name="lab_complete"),
]
