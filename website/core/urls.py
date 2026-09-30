from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("curriculum/", views.curriculum, name="curriculum"),
    path("partners/", views.partners, name="partners"),
    path("impact/", views.impact, name="impact"),
    path("contact/", views.contact, name="contact"),
    path("newsletter/subscribe/", views.subscribe_newsletter, name="subscribe_newsletter"),
]
