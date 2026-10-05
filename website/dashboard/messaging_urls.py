from django.urls import path

from . import messaging_views as views

app_name = "messaging"

urlpatterns = [
    path("", views.inbox, name="inbox"),
    path("new/", views.compose, name="compose"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/reply/", views.reply, name="reply"),
]
