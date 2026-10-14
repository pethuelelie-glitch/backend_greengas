from django.urls import path
from apps.energie.views import (
    ProductionListView,
    ProductionGlobaleView,
    ProductionDetailView,
    ProductionCloturerView,
    SiteMesuresView,
    AlerteListView,
    AlerteDetailView,
    AlerteResoudreView,
)

urlpatterns = [
    # Productions (/api/v1/productions/...)
    path('productions/', ProductionListView.as_view(), name='productions_list'),
    path('productions/globale/', ProductionGlobaleView.as_view(), name='productions_globale'),
    path('productions/<uuid:id>/', ProductionDetailView.as_view(), name='productions_detail'),
    path('productions/<uuid:id>/cloturer/', ProductionCloturerView.as_view(), name='productions_cloturer'),

    # Mesures journalières de site (/api/v1/sites/{id}/mesures/)
    path('sites/<uuid:id>/mesures/', SiteMesuresView.as_view(), name='sites_mesures_envoyer'),

    # Alertes (/api/v1/alertes/...)
    path('alertes/', AlerteListView.as_view(), name='alertes_list'),
    path('alertes/<uuid:id>/', AlerteDetailView.as_view(), name='alertes_detail'),
    path('alertes/<uuid:id>/resoudre/', AlerteResoudreView.as_view(), name='alertes_resoudre'),
]
