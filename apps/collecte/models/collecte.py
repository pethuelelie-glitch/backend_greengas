import uuid
from django.db import models


class StatutCollecte(models.TextChoices):
    EN_ATTENTE_PESEE = 'en_attente_pesee', 'En attente de pesée'
    PESEE = 'pesee', 'Pesée reçue'
    VALIDEE = 'validee', 'Validée'


class StatutControle(models.TextChoices):
    NORMAL = 'normal', 'Normal'
    A_VERIFIER = 'a_verifier', 'À vérifier'
    POINTS_VALIDES = 'points_valides', 'Points validés'
    POINTS_ANNULES = 'points_annules', 'Points annulés'


class SourceMesure(models.TextChoices):
    SIMULE = 'simule', 'Simulé'
    CAPTEUR = 'capteur', 'Capteur réel'


class Collecte(models.Model):
    """Collecte d'un bac lors d'une tournée"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tournee = models.ForeignKey(
        'collecte.Tournee',
        on_delete=models.PROTECT,
        related_name='collectes',
        verbose_name="Tournée"
    )
    bac = models.ForeignKey(
        'referentiel.Bac',
        on_delete=models.PROTECT,
        related_name='collectes',
        verbose_name="Bac"
    )
    collecteur = models.ForeignKey(
        'comptes.Utilisateur',
        on_delete=models.PROTECT,
        related_name='collectes',
        verbose_name="Collecteur"
    )
    statut = models.CharField(
        max_length=20,
        choices=StatutCollecte.choices,
        default=StatutCollecte.EN_ATTENTE_PESEE,
        verbose_name="Statut"
    )

    # Pesée
    poids_brut_kg = models.DecimalField(
        max_digits=7, decimal_places=2,
        null=True, blank=True,
        verbose_name="Poids brut (kg)"
    )
    tare_kg = models.DecimalField(
        max_digits=6, decimal_places=2,
        verbose_name="Tare (kg) — copié du bac"
    )
    # Champs calculés par le backend
    poids_net_kg = models.DecimalField(
        max_digits=7, decimal_places=2,
        null=True, blank=True,
        verbose_name="Poids net (kg)"
    )
    source = models.CharField(
        max_length=10,
        choices=SourceMesure.choices,
        null=True, blank=True,
        verbose_name="Source de la mesure"
    )

    # Contrôle antifraude (figé à la validation)
    scans_valides = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name="Scans valides sur la période"
    )
    kg_par_scan = models.DecimalField(
        max_digits=6, decimal_places=3,
        null=True, blank=True,
        verbose_name="kg par scan"
    )
    statut_controle = models.CharField(
        max_length=20,
        choices=StatutControle.choices,
        null=True, blank=True,
        verbose_name="Statut de contrôle"
    )

    # Horodatages
    date_ouverture = models.DateTimeField(auto_now_add=True, verbose_name="Date d'ouverture")
    date_pesee = models.DateTimeField(null=True, blank=True, verbose_name="Date de pesée")
    date_validation = models.DateTimeField(null=True, blank=True, verbose_name="Date de validation")

    class Meta:
        db_table = 'collecte_collecte'
        verbose_name = 'Collecte'
        verbose_name_plural = 'Collectes'
        unique_together = [('tournee', 'bac')]  # Un bac = une collecte par tournée
        ordering = ['-date_ouverture']

    def __str__(self):
        return f"Collecte {self.bac} / {self.tournee.code} [{self.get_statut_display()}]"
