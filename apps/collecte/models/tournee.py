import uuid
from django.db import models


class MotifAffectation(models.TextChoices):
    SECTEUR = 'secteur', 'Site du secteur'
    REPLI = 'repli', 'Site de repli (maintenance)'


class StatutTournee(models.TextChoices):
    PLANIFIEE = 'planifiee', 'Planifiée'
    EN_COURS = 'en_cours', 'En cours'
    COLLECTEE = 'collectee', 'Collectée'
    TRIEE = 'triee', 'Triée'


class NiveauContamination(models.TextChoices):
    FAIBLE = 'faible', 'Faible'
    MOYEN = 'moyen', 'Moyen'
    ELEVE = 'eleve', 'Élevé'


class Tournee(models.Model):
    """Tournée de collecte d'un secteur pour une journée"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(
        max_length=20, unique=True,
        verbose_name="Code tournée (ex: TRN-0912-01)"
    )
    date = models.DateField(verbose_name="Date de la tournée")
    secteur = models.ForeignKey(
        'referentiel.Secteur',
        on_delete=models.PROTECT,
        related_name='tournees',
        verbose_name="Secteur"
    )
    # Site calculé à la création selon le statut du site normal du secteur
    site = models.ForeignKey(
        'referentiel.Site',
        on_delete=models.PROTECT,
        related_name='tournees',
        verbose_name="Site de destination"
    )
    motif_affectation = models.CharField(
        max_length=10,
        choices=MotifAffectation.choices,
        default=MotifAffectation.SECTEUR,
        verbose_name="Motif d'affectation au site"
    )
    collecteur = models.ForeignKey(
        'comptes.Utilisateur',
        on_delete=models.PROTECT,
        related_name='tournees',
        verbose_name="Collecteur assigné"
    )
    statut = models.CharField(
        max_length=15,
        choices=StatutTournee.choices,
        default=StatutTournee.PLANIFIEE,
        verbose_name="Statut"
    )
    niveau_contamination = models.CharField(
        max_length=10,
        choices=NiveauContamination.choices,
        null=True, blank=True,
        verbose_name="Niveau de contamination (saisi au tri)"
    )
    bacs = models.ManyToManyField(
        'referentiel.Bac',
        related_name='tournees',
        verbose_name="Bacs prévus"
    )

    class Meta:
        db_table = 'collecte_tournee'
        verbose_name = 'Tournée'
        verbose_name_plural = 'Tournées'
        ordering = ['-date', 'code']

    def __str__(self):
        return f"{self.code} — {self.date} ({self.get_statut_display()})"
