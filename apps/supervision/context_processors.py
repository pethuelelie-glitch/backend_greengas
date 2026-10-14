"""
Context processors pour le dashboard admin GREENGAS.
Fournit les métriques réelles (KPIs) issues de la base de données.
AUCUNE donnée de démonstration / fake data : uniquement les données réelles du système.
"""


def greengas_stats(request):
    """
    Injecte les statistiques opérationnelles réelles dans le contexte
    des pages d'administration.
    """
    if not request.path.startswith('/greengas/'):
        return {}

    try:
        from apps.comptes.models import Utilisateur
        from apps.referentiel.models import Site, Bac
        from apps.collecte.models import Tournee, Scan
        from apps.energie.models import Alerte, ProductionEnergie
        from apps.greenpoints.models import GreenPointsTransaction

        return {
            'gg_stats': {
                'utilisateurs_total': Utilisateur.objects.count(),
                'sites_total': Site.objects.count(),
                'bacs_total': Bac.objects.count(),
                'tournees_total': Tournee.objects.count(),
                'scans_total': Scan.objects.count(),
                'alertes_actives': Alerte.objects.filter(statut='active').count(),
                'productions_total': ProductionEnergie.objects.count(),
                'transactions_total': GreenPointsTransaction.objects.count(),
            }
        }
    except Exception:
        return {'gg_stats': {}}
