from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("login/", views.CloudForKidsLoginView.as_view(), name="login"),
    path("logout/", views.CloudForKidsLogoutView.as_view(), name="logout"),
    path("profile/", views.profile, name="profile"),
    path("classes/join/", views.join_class, name="join_class"),
    path("classes/<int:class_id>/leave/", views.leave_class, name="leave_class"),
]
