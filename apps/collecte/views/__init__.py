from .scan_views import ScanListCreateView
from .tournee_views import (
    TourneeListCreateView,
    TourneeDetailView,
    TourneeDemarrerView,
    TourneeCollecteOuvrirView,
    TourneeCloturerView,
)
from .collecte_views import (
    CollecteListView,
    CollecteDetailView,
    CollectePeseeView,
    CollecteValiderView,
    CollecteDecisionView,
)

__all__ = [
    'ScanListCreateView',
    'TourneeListCreateView',
    'TourneeDetailView',
    'TourneeDemarrerView',
    'TourneeCollecteOuvrirView',
    'TourneeCloturerView',
    'CollecteListView',
    'CollecteDetailView',
    'CollectePeseeView',
    'CollecteValiderView',
    'CollecteDecisionView',
]
