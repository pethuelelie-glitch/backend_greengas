from django.contrib import admin
from django.urls import path, include
from backend_greengas.views import SwaggerUIView, RedocView, OpenAPISchemaView

urlpatterns = [
    # Documentation interactive Swagger UI & ReDoc
    path('api/docs/', SwaggerUIView.as_view(), name='swagger_ui'),
    path('api/redoc/', RedocView.as_view(), name='redoc'),
    path('api/schema/', OpenAPISchemaView.as_view(), name='openapi_schema'),

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

