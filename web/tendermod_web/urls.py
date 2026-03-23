from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(url='/redneet/', permanent=False)),
    path('redneet/', include('apps.redneet.urls')),
    path('analysis/', include('apps.analysis.urls')),
    path('api/', include('apps.core.api_urls')),
]
