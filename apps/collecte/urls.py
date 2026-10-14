from django.urls import path

from apps.collecte.views import (
    ScanListCreateView,
    TourneeListCreateView,
    TourneeDetailView,
    TourneeDemarrerView,
    TourneeCollecteOuvrirView,
    TourneeCloturerView,
    CollecteListView,
    CollecteDetailView,
    CollectePeseeView,
    CollecteValiderView,
    CollecteDecisionView,
)

urlpatterns = [
    # Scans (/api/v1/scans/...)
    path('scans/', ScanListCreateView.as_view(), name='scan_list_create'),

    # Tournées (/api/v1/tournees/...)
    path('tournees/', TourneeListCreateView.as_view(), name='tournee_list_create'),
    path('tournees/<uuid:id>/', TourneeDetailView.as_view(), name='tournee_detail'),
    path('tournees/<uuid:id>/demarrer/', TourneeDemarrerView.as_view(), name='tournee_demarrer'),
    path('tournees/<uuid:id>/collectes/', TourneeCollecteOuvrirView.as_view(), name='tournee_collecte_ouvrir'),
    path('tournees/<uuid:id>/cloturer/', TourneeCloturerView.as_view(), name='tournee_cloturer'),

    # Collectes (/api/v1/collectes/...)
    path('collectes/', CollecteListView.as_view(), name='collecte_list'),
    path('collectes/<uuid:id>/', CollecteDetailView.as_view(), name='collecte_detail'),
    path('collectes/<uuid:id>/pesee/', CollectePeseeView.as_view(), name='collecte_pesee'),
    path('collectes/<uuid:id>/valider/', CollecteValiderView.as_view(), name='collecte_valider'),
    path('collectes/<uuid:id>/decision/', CollecteDecisionView.as_view(), name='collecte_decision'),
]
