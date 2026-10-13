import uuid
from django.db import models


class StatutBac(models.TextChoices):
    ACTIF = 'actif', 'Actif'
    INACTIF = 'inactif', 'Inactif'


class Bac(models.Model):
    """Bac de collecte des déchets"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code bac (ex: BAC-014)")
    residence = models.CharField(max_length=150, verbose_name="Résidence / Emplacement")
    secteur = models.ForeignKey(
        'referentiel.Secteur',
        on_delete=models.PROTECT,
        related_name='bacs',
        verbose_name="Secteur"
    )
    nb_foyers_declares = models.PositiveIntegerField(verbose_name="Nombre de foyers déclarés")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, verbose_name="Latitude")
    longitude = models.DecimalField(max_digits=9, decimal_places=6, verbose_name="Longitude")
    tare_kg = models.DecimalField(max_digits=6, decimal_places=2, verbose_name="Tare (poids à vide en kg)")
    capacite_kg = models.DecimalField(max_digits=6, decimal_places=2, verbose_name="Capacité (kg)")
    statut = models.CharField(
        max_length=20,
        choices=StatutBac.choices,
        default=StatutBac.ACTIF,
        verbose_name="Statut"
    )
    date_derniere_collecte = models.DateTimeField(null=True, blank=True, verbose_name="Dernière collecte")

    class Meta:
        db_table = 'referentiel_bac'
        verbose_name = 'Bac'
        verbose_name_plural = 'Bacs'
        ordering = ['code']

    def __str__(self):
        return f"{self.code} ({self.residence})"
