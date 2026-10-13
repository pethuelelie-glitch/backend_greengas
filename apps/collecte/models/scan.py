import uuid
from django.db import models


class StatutScan(models.TextChoices):
    VALIDE = 'valide', 'Valide'
    NON_LOCALISE = 'non_localise', 'Non localisé'
    HORS_ZONE = 'hors_zone', 'Hors zone'
    REFUSE_PLAFOND = 'refuse_plafond', 'Refusé (plafond)'


class Scan(models.Model):
    """Scan du QR code d'un bac par un citoyen"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    citoyen = models.ForeignKey(
        'comptes.Utilisateur',
        on_delete=models.PROTECT,
        related_name='scans',
        verbose_name="Citoyen"
    )
    bac = models.ForeignKey(
        'referentiel.Bac',
        on_delete=models.PROTECT,
        related_name='scans',
        verbose_name="Bac"
    )
    horodatage = models.DateTimeField(auto_now_add=True, verbose_name="Horodatage")
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6,
        null=True, blank=True,
        verbose_name="Latitude"
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6,
        null=True, blank=True,
        verbose_name="Longitude"
    )
    # Champs calculés par le backend
    distance_m = models.DecimalField(
        max_digits=8, decimal_places=2,
        null=True, blank=True,
        verbose_name="Distance au bac (m)"
    )
    statut = models.CharField(
        max_length=20,
        choices=StatutScan.choices,
        default=StatutScan.VALIDE,
        verbose_name="Statut"
    )
    compte = models.BooleanField(
        default=True,
        verbose_name="Compte dans la répartition"
    )

    class Meta:
        db_table = 'collecte_scan'
        verbose_name = 'Scan'
        verbose_name_plural = 'Scans'
        ordering = ['-horodatage']

    def __str__(self):
        return f"Scan {self.citoyen} → {self.bac} [{self.statut}]"
