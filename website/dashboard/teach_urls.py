from django.urls import path

from . import teach_views as views

app_name = "teach"

urlpatterns = [
    path("", views.home, name="home"),
    path("class/new/", views.class_new, name="class_new"),
    path("class/<int:class_id>/", views.class_detail, name="class"),
    path("class/<int:class_id>/edit/", views.class_edit, name="class_edit"),
    path("class/<int:class_id>/archive/", views.class_archive, name="class_archive"),
    path("class/<int:class_id>/export.csv", views.class_export, name="class_export"),
    path("class/<int:class_id>/learner/<int:learner_id>/", views.learner_report, name="learner"),
    path("class/<int:class_id>/learner/<int:learner_id>/remove/", views.member_remove, name="member_remove"),
    path("class/<int:class_id>/sessions/add/", views.session_add, name="session_add"),
    path("class/<int:class_id>/sessions/<int:session_id>/delete/", views.session_delete, name="session_delete"),
    path("class/<int:class_id>/assign/", views.assignment_add, name="assignment_add"),
    path("class/<int:class_id>/assign/<int:assignment_id>/delete/", views.assignment_delete, name="assignment_delete"),
    path("curriculum/", views.curriculum, name="curriculum"),
]
