from django.urls import path

from . import family_views as views

app_name = "family"

urlpatterns = [
    path("", views.home, name="home"),
    path("add/", views.add_child, name="add"),
    path("child/<int:child_id>/", views.child_detail, name="child"),
    path("child/<int:child_id>/remove/", views.remove_child, name="remove"),
]
