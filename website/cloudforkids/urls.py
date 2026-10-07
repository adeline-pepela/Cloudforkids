"""
URL configuration for cloudforkids project.
"""
from django.contrib import admin
from core import admin_tools
from django.urls import include, path, re_path
from django.conf import settings
from core.media import serve_media

urlpatterns = [
    path('i18n/', include('django.conf.urls.i18n')),
    path('admin/tools/', include((admin_tools.urls(), 'tools'))),
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('teach/', include('dashboard.teach_urls')),
    path('messages/', include('dashboard.messaging_urls')),
    path('family/', include('dashboard.family_urls')),
    path('dashboard/', include('dashboard.urls')),
    path('learn/', include('courses.urls')),
    re_path(r'^%s(?P<path>.*)$' % settings.MEDIA_URL.lstrip('/'), serve_media),
    path('', include('core.urls')),
]
