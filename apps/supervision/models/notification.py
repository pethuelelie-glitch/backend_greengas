import uuid
from django.db import models
from django.utils import timezone
from apps.supervision.models.journal import TypeObjet


class TypeNotification(models.TextChoices):
    TOURNEE_A_TRIER = 'tournee_a_trier', 'Tournée à trier'
    ALERTE_OUVERTE = 'alerte_ouverte', 'Alerte ouverte'
    ALERTE_REPETEE = 'alerte_repetee', 'Alerte répétée'
    SITE_MAINTENANCE = 'site_maintenance', 'Maintenance site'
    COMPTE_A_VALIDER = 'compte_a_valider', 'Compte à valider'
    COLLECTE_A_VERIFIER = 'collecte_a_verifier', 'Collecte à vérifier'
    BAC_SURINSCRIT = 'bac_surinscrit', 'Bac surinscrit'
    POINTS_CREDITES = 'points_credites', 'Points crédités'
    POINTS_EN_ATTENTE = 'points_en_attente', 'Points en attente'
    POINTS_ANNULES = 'points_annules', 'Points annulés'
    ECHANGE_EFFECTUE = 'echange_effectue', 'Échange effectué'
    TOURNEE_PLANIFIEE = 'tournee_planifiee', 'Tournée planifiée'


class NiveauNotification(models.TextChoices):
    INFO = 'info', 'Information'
    ATTENTION = 'attention', 'Attention'
    CRITIQUE = 'critique', 'Critique'


class Notification(models.Model):
    """
    Notification adressée à un utilisateur suite à un événement système.
    Contrat 1.4.0 (SIREXE Hackathon 2026).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    destinataire = models.ForeignKey(
        'comptes.Utilisateur',
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name="Destinataire"
    )
    type = models.CharField(
        max_length=30,
        choices=TypeNotification.choices,
        verbose_name="Type de notification"
    )
    niveau = models.CharField(
        max_length=15,
        choices=NiveauNotification.choices,
        default=NiveauNotification.INFO,
        verbose_name="Niveau d'importance"
    )
    titre = models.CharField(max_length=80, verbose_name="Titre")
    message = models.TextField(verbose_name="Message")
    objet_type = models.CharField(
        max_length=30,
        choices=TypeObjet.choices,
        null=True, blank=True,
        verbose_name="Type d'objet"
    )
    objet_id = models.UUIDField(
        null=True, blank=True,
        verbose_name="Identifiant de l'objet"
    )
    lue = models.BooleanField(default=False, verbose_name="Notification lue")
    date_creation = models.DateTimeField(default=timezone.now, verbose_name="Date de création")
    date_lecture = models.DateTimeField(null=True, blank=True, verbose_name="Date de lecture")

    class Meta:
        db_table = 'supervision_notification'
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        ordering = ['-date_creation']
        indexes = [
            models.Index(fields=['destinataire', 'lue', 'date_creation']),
        ]

    def __str__(self):
        return f"[{self.get_niveau_display()}] {self.titre} → {self.destinataire.nom}"
