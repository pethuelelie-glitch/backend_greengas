import logging
from django.utils import timezone
from apps.supervision.models import Notification, TypeNotification, NiveauNotification
from apps.comptes.models import Role

logger = logging.getLogger(__name__)


def creer_notification(destinataire, type, niveau, titre, message, objet_type=None, objet_id=None, date_creation=None, auteur=None):
    """
    Crée une notification pour un utilisateur si toutes les règles métier sont respectées :
    1. Le compte technique 'capteur' ne reçoit aucune notification.
    2. L'auteur de l'action n'est pas notifié de sa propre action.
    3. Pas de doublon pour 'bac_surinscrit' et 'collecte_a_verifier' si une notification non-lue existe déjà.
    """
    if not destinataire:
        return None

    # Règle : pas de notification pour le compte capteur
    if getattr(destinataire, 'role', None) == Role.CAPTEUR:
        return None

    # Règle : pas de notification à l'auteur de l'action
    if auteur and getattr(destinataire, 'id', None) == getattr(auteur, 'id', None):
        return None

    # Règle anti-doublon pour bac_surinscrit et collecte_a_verifier
    if type in [TypeNotification.BAC_SURINSCRIT, TypeNotification.COLLECTE_A_VERIFIER]:
        existe_non_lue = Notification.objects.filter(
            destinataire=destinataire,
            type=type,
            objet_type=objet_type,
            objet_id=objet_id,
            lue=False
        ).exists()
        if existe_non_lue:
            return None

    kwargs = {
        'destinataire': destinataire,
        'type': type,
        'niveau': niveau,
        'titre': titre[:80],
        'message': message,
        'objet_type': objet_type,
        'objet_id': objet_id,
        'lue': False,
    }
    if date_creation:
        kwargs['date_creation'] = date_creation

    try:
        notif = Notification.objects.create(**kwargs)
        return notif
    except Exception as e:
        logger.warning(f"Impossible de créer la notification pour {destinataire}: {e}")
        return None


def notifier_utilisateurs(destinataires, type, niveau, titre, message, objet_type=None, objet_id=None, date_creation=None, auteur=None):
    """
    Notifie une liste d'utilisateurs ou un QuerySet.
    """
    notifs = []
    for user in destinataires:
        n = creer_notification(
            destinataire=user,
            type=type,
            niveau=niveau,
            titre=titre,
            message=message,
            objet_type=objet_type,
            objet_id=objet_id,
            date_creation=date_creation,
            auteur=auteur
        )
        if n:
            notifs.append(n)
    return notifs
