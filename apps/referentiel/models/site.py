import uuid
from django.db import models


class StatutSite(models.TextChoices):
    NOMINAL = 'nominal', 'Nominal'
    ALERTE = 'alerte', 'Alerte'
    MAINTENANCE = 'maintenance', 'Maintenance'


class Site(models.Model):
    """Site de méthanisation (digesteur)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code (ex: DIG-01)")
    nom = models.CharField(max_length=150, verbose_name="Nom du site")
    statut = models.CharField(
        max_length=20,
        choices=StatutSite.choices,
        default=StatutSite.NOMINAL,
        verbose_name="Statut"
    )
    capacite_kg_jour = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Capacité (kg/jour)")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, verbose_name="Latitude")
    longitude = models.DecimalField(max_digits=9, decimal_places=6, verbose_name="Longitude")

    class Meta:
        db_table = 'referentiel_site'
        verbose_name = 'Site méthaniseur'
        verbose_name_plural = 'Sites méthaniseurs'

    def __str__(self):
        return f"{self.code} - {self.nom} ({self.get_statut_display()})"
