from rest_framework_simplejwt.authentication import JWTAuthentication
from apps.comptes.models import StatutValidation
from apps.comptes.exceptions import CompteNonValideException
from apps.comptes.utils import is_validation_personnel_active


class CustomJWTAuthentication(JWTAuthentication):
    """
    Authentification JWT avec vérification continue du statut du compte.
    Contrat 1.5.0 :
    - Si la validation du personnel est activée (validation_comptes_personnel = 1),
      un compte encore en attente est immédiatement déconnecté (403 COMPTE_NON_VALIDE)
      à sa requête suivante.
    - Dans tous les cas, un compte refusé ou inactif (actif = false) reste refusé.
    """
    def get_user(self, validated_token):
        user = super().get_user(validated_token)

        if not user.actif:
            raise CompteNonValideException(
                message="Ce compte est désactivé.",
                details={"actif": False}
            )

        if user.statut_validation == StatutValidation.REFUSE:
            raise CompteNonValideException(
                message="Votre demande d'accès a été refusée.",
                details={"statut_validation": "refuse"}
            )

        if user.statut_validation == StatutValidation.EN_ATTENTE and is_validation_personnel_active():
            raise CompteNonValideException(
                message="Votre compte attend la validation d'un administrateur.",
                details={"statut_validation": "en_attente"}
            )

        return user
