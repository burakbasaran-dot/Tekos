from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static

from core.urls import platform_urlpatterns
from core.urls_signup import legal_urlpatterns, signup_urlpatterns

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include((signup_urlpatterns, 'signup'))),
    path('accounts/', include('django.contrib.auth.urls')),
    path('legal/', include((legal_urlpatterns, 'legal'))),
    path('api/', include('core.urls')),
    path('platform/', include((platform_urlpatterns, 'core'))),
    path('stok/', include('stokapp.urls')),
    path('', RedirectView.as_view(url='/stok/dashboard/')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
