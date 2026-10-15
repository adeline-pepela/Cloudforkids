from django.urls import path

from . import views

app_name = "live"

urlpatterns = [
    path("webhook/", views.webhook, name="webhook"),
    path("class/<int:class_id>/start/", views.start, name="start"),
    path("session/<int:session_id>/report/", views.report, name="report"),
    path("recording/<int:recording_id>/", views.recording, name="recording"),
    path("<str:code>/", views.room_page, name="room"),
    path("<str:code>/token/", views.token, name="token"),
    path("<str:code>/status/", views.status, name="status"),
    path("<str:code>/hand/", views.hand, name="hand"),
    path("<str:code>/chat/", views.chat, name="chat"),
    path("<str:code>/react/", views.react, name="react"),
    path("<str:code>/vote/", views.vote, name="vote"),
    path("<str:code>/results/", views.results, name="results"),
    path("<str:code>/control/", views.control, name="control"),
]
