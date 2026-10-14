from django.urls import path
from apps.referentiel.views import (
    SiteListView,
    SiteDetailUpdateView,
    SecteurListView,
    SecteurDetailUpdateView,
    BacListCreateView,
    BacDetailUpdateView,
)

urlpatterns = [
    # Sites (/api/v1/sites/...)
    path('sites/', SiteListView.as_view(), name='sites_list'),
    path('sites/<uuid:id>/', SiteDetailUpdateView.as_view(), name='sites_detail'),

    # Secteurs (/api/v1/secteurs/...)
    path('secteurs/', SecteurListView.as_view(), name='secteurs_list'),
    path('secteurs/<uuid:id>/', SecteurDetailUpdateView.as_view(), name='secteurs_detail'),

    # Bacs (/api/v1/bacs/...)
    path('bacs/', BacListCreateView.as_view(), name='bacs_list'),
    path('bacs/<uuid:id>/', BacDetailUpdateView.as_view(), name='bacs_detail'),
]
