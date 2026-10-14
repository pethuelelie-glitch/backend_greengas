from decimal import Decimal


def is_validation_personnel_active() -> bool:
    """
    Renvoie True si la validation des comptes du personnel par un administrateur est activée.
    Contrat 1.5.0 :
    - 1 = validation activée (statut_validation = en_attente, notification émise, 403 à la connexion)
    - 0 = désactivée (statut_validation = valide, pas de notification, connexion autorisée)
    Valeur par défaut : True (validation activée, comportement fermé en cas d'erreur).
    """
    try:
        from apps.supervision.models import Parametre
        param = Parametre.objects.filter(cle='validation_comptes_personnel').first()
        if param and param.valeur is not None:
            return Decimal(str(param.valeur)) == Decimal('1')
    except Exception:
        pass
    return True
