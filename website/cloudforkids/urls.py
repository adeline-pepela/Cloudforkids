"""
URL configuration for cloudforkids project.
"""
from django.contrib import admin
from core import admin_tools
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

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
    path('', include('core.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
