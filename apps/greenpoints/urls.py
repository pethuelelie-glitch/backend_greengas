from django.urls import path
from apps.greenpoints.views import (
    GreenPointsSoldeView,
    GreenPointsTransactionListView,
    RecompenseListCreateView,
    RecompenseDetailView,
    EchangeListCreateView,
)

urlpatterns = [
    path('greenpoints/solde/', GreenPointsSoldeView.as_view(), name='greenpoints_solde'),
    path('greenpoints/transactions/', GreenPointsTransactionListView.as_view(), name='greenpoints_transactions_lister'),
    path('recompenses/', RecompenseListCreateView.as_view(), name='recompenses_lister_creer'),
    path('recompenses/<uuid:id>/', RecompenseDetailView.as_view(), name='recompenses_detail_modifier'),
    path('echanges/', EchangeListCreateView.as_view(), name='echanges_lister_creer'),
]
