import math
from decimal import Decimal
from typing import Optional


def calculer_distance_haversine(lat1, lon1, lat2, lon2) -> float:
    """
    Calcule la distance en mètres entre deux coordonnées géographiques
    selon la formule Haversine (Rayon terrestre = 6 371 000 m).
    """
    r = 6371000.0
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    delta_phi = math.radians(float(lat2) - float(lat1))
    delta_lambda = math.radians(float(lon2) - float(lon1))

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.asin(math.sqrt(a))
    return r * c


def get_parametre(cle: str, default: float) -> float:
    """
    Lit un paramètre système depuis la table Parametre (supervision).
    Retourne la valeur par défaut si le paramètre est absent ou inaccessible.
    """
    try:
        from apps.supervision.models import Parametre
        param = Parametre.objects.filter(cle=cle).first()
        if param is not None and param.valeur is not None:
            return float(param.valeur)
    except Exception:
        pass
    return float(default)
