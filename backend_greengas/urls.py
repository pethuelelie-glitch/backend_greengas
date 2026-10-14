from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # Dashboard Admin
    path('greengas/', admin.site.urls),

    # API REST v1
    path('api/v1/', include('apps.comptes.urls')),
    path('api/v1/', include('apps.referentiel.urls')),
    path('api/v1/', include('apps.collecte.urls')),
    path('api/v1/', include('apps.tri.urls')),
    path('api/v1/', include('apps.greenpoints.urls')),
    path('api/v1/', include('apps.energie.urls')),
    path('api/v1/', include('apps.supervision.urls')),
    path('api/v1/', include('apps.simulateur.urls')),
]
