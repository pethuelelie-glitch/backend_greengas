from django.urls import path
from apps.supervision.views import (
    VerificationQueueView,
    ParametreListView,
    ParametreDetailUpdateView,
    JournalAuditListView,
    BacTracabiliteView,
)

urlpatterns = [
    # File de vérification antifraude (/api/v1/verifications/)
    path('verifications/', VerificationQueueView.as_view(), name='verifications_queue'),

    # Paramètres système (/api/v1/parametres/...)
    path('parametres/', ParametreListView.as_view(), name='parametres_list'),
    path('parametres/<str:cle>/', ParametreDetailUpdateView.as_view(), name='parametres_detail_update'),

    # Journal d'audit (/api/v1/journal/)
    path('journal/', JournalAuditListView.as_view(), name='journal_audit_list'),

    # Traçabilité d'un bac (/api/v1/bacs/{id}/tracabilite/)
    path('bacs/<uuid:id>/tracabilite/', BacTracabiliteView.as_view(), name='bac_tracabilite'),
]

