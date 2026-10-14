from django.urls import path
from apps.comptes.views import (
    ConnexionView,
    MoiView,
    InscriptionCitoyenView,
    InscriptionPersonnelView,
    OtpVerifierView,
    OtpRenvoyerView,
    CustomTokenRefreshView,
    TokenRevokeView,
    UtilisateurListCreateView,
    UtilisateurDetailView,
    UtilisateurValidationView,
)

urlpatterns = [
    # Authentification (/api/v1/auth/...)
    path('auth/token/', ConnexionView.as_view(), name='auth_token'),
    path('auth/token/rafraichir/', CustomTokenRefreshView.as_view(), name='auth_token_rafraichir'),
    path('auth/deconnexion/', TokenRevokeView.as_view(), name='auth_deconnexion'),
    path('auth/moi/', MoiView.as_view(), name='auth_moi'),
    path('auth/inscription/', InscriptionCitoyenView.as_view(), name='auth_inscription'),
    path('auth/inscription/personnel/', InscriptionPersonnelView.as_view(), name='auth_inscription_personnel'),
    path('auth/otp/verifier/', OtpVerifierView.as_view(), name='auth_otp_verifier'),
    path('auth/otp/renvoyer/', OtpRenvoyerView.as_view(), name='auth_otp_renvoyer'),

    # Utilisateurs (/api/v1/utilisateurs/...)
    path('utilisateurs/', UtilisateurListCreateView.as_view(), name='utilisateurs_list'),
    path('utilisateurs/<uuid:id>/', UtilisateurDetailView.as_view(), name='utilisateurs_detail'),
    path('utilisateurs/<uuid:id>/validation/', UtilisateurValidationView.as_view(), name='utilisateurs_validation'),
]
