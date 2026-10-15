from django.urls import path

from . import views

app_name = "assistant"

urlpatterns = [
    path("state/", views.state, name="state"),
    path("send/", views.send, name="send"),
    path("threads/<int:pk>/", views.thread_detail, name="thread"),
    path("threads/<int:pk>/stop/", views.stop, name="stop"),
    path("threads/<int:pk>/delete/", views.delete_thread, name="delete"),
    path("actions/<int:pk>/decide/", views.decide, name="decide"),
    path("actions/<int:pk>/undo/", views.undo, name="undo"),
]
