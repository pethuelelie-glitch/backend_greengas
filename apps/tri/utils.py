import math
from decimal import Decimal
from apps.tri.models.lot_trie import LotTrie, Categorie


PREFIX_PAR_CATEGORIE = {
    Categorie.ORGANIQUE: 'ORG',
    Categorie.BIOMASSE: 'BIO',
    Categorie.PLASTIQUE: 'PLA',
    Categorie.METAL: 'MET',
    Categorie.CARTON_PAPIER: 'CAR',
    Categorie.VERRE: 'VER',
    Categorie.REFUS: 'REF',
}


def get_parametre(cle: str, default: Decimal | float | int) -> Decimal:
    """
    Lit un paramètre système depuis la table Parametre (supervision).
    Retourne la valeur par défaut sous forme de Decimal si le paramètre est absent ou inaccessible.
    """
    try:
        from apps.supervision.models import Parametre
        param = Parametre.objects.filter(cle=cle).first()
        if param is not None and param.valeur is not None:
            return Decimal(str(param.valeur))
    except Exception:
        pass
    return Decimal(str(default))


def generer_code_lot(categorie: str) -> str:
    """
    Génère un code lot unique selon le format (ORG-0258, PLA-0001, etc.).
    """
    prefix = PREFIX_PAR_CATEGORIE.get(categorie, 'LOT')
    existing_lots = LotTrie.objects.filter(code_lot__startswith=f"{prefix}-").values_list('code_lot', flat=True)
    max_num = 0
    for code in existing_lots:
        try:
            parts = code.split('-')
            if len(parts) >= 2:
                num = int(parts[1])
                if num > max_num:
                    max_num = num
        except (IndexError, ValueError):
            pass

    next_num = max_num + 1
    code_lot = f"{prefix}-{next_num:04d}"
    while LotTrie.objects.filter(code_lot=code_lot).exists():
        next_num += 1
        code_lot = f"{prefix}-{next_num:04d}"
    return code_lot
