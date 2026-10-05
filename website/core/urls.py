from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("find-your-path/", views.find_path, name="find_path"),
    path("how-the-cloud-works/", views.cloud_demo, name="cloud_demo"),
    path("about/", views.about, name="about"),
    path("curriculum/", views.curriculum, name="curriculum"),
    path("partners/", views.partners, name="partners"),
    path("impact/", views.impact, name="impact"),
    path("contact/", views.contact, name="contact"),
    path("terms/", views.legal, {"slug": "terms"}, name="terms"),
    path("privacy/", views.legal, {"slug": "privacy"}, name="privacy"),
    path("newsletter/subscribe/", views.subscribe_newsletter, name="subscribe_newsletter"),
]
