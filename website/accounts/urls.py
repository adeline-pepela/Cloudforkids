from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("login/", views.CloudForKidsLoginView.as_view(), name="login"),
    path("logout/", views.CloudForKidsLogoutView.as_view(), name="logout"),
    path("profile/", views.profile, name="profile"),
    path("consent/waiting/", views.consent_pending, name="consent_pending"),
    path("consent/<str:token>/", views.consent_review, name="consent"),
    path("unsubscribe/<str:token>/", views.unsubscribe, name="unsubscribe"),
    path("password-reset/", views.CloudForKidsPasswordResetView.as_view(), name="password_reset"),
    path("password-reset/sent/", views.CloudForKidsPasswordResetDoneView.as_view(), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", views.CloudForKidsPasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("reset/done/", views.CloudForKidsPasswordResetCompleteView.as_view(), name="password_reset_complete"),
    path("classes/join/", views.join_class, name="join_class"),
    path("classes/<int:class_id>/leave/", views.leave_class, name="leave_class"),
]
