import uuid
from django.db import models


class StatutJournee(models.TextChoices):
    OUVERTE = 'ouverte', 'Ouverte'
    CLOTUREE = 'cloturee', 'Clôturée'


class DestinationDigestat(models.TextChoices):
    VENTE_AGRICOLE = 'vente_agricole', 'Vente agricole'
    STOCKAGE = 'stockage', 'Stockage'


class StatutDonnee(models.TextChoices):
    MESURE = 'mesure', 'Mesuré'
    ESTIME = 'estime', 'Estimé'
    SIMULE = 'simule', 'Simulé'


class ProductionEnergie(models.Model):
    """Bilan de production énergétique d'un site digesteur pour une journée"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.ForeignKey(
        'referentiel.Site',
        on_delete=models.PROTECT,
        related_name='productions',
        verbose_name="Site digesteur"
    )
    date = models.DateField(verbose_name="Date de production")
    statut_journee = models.CharField(
        max_length=10,
        choices=StatutJournee.choices,
        default=StatutJournee.OUVERTE,
        verbose_name="Statut de la journée"
    )

    # Intrants organiques (cumulés lors du tri)
    poids_organique_recu_kg = models.DecimalField(
        max_digits=9, decimal_places=2,
        default=0,
        verbose_name="Poids organique reçu (kg)"
    )

    # Champs calculés par le backend
    biogaz_attendu_m3 = models.DecimalField(
        max_digits=9, decimal_places=2,
        default=0,
        verbose_name="Biogaz attendu (m³)"
    )

    # Mesures envoyées par le capteur / simulateur
    biogaz_mesure_m3 = models.DecimalField(
        max_digits=9, decimal_places=2,
        null=True, blank=True,
        verbose_name="Biogaz mesuré (m³)"
    )
    ch4_pct = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        verbose_name="Teneur en CH₄ (%)"
    )
    temperature_c = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        verbose_name="Température (°C)"
    )
    ph = models.DecimalField(
        max_digits=4, decimal_places=2,
        null=True, blank=True,
        verbose_name="pH"
    )

    # Champs calculés après réception de la mesure
    ecart_pct = models.DecimalField(
        max_digits=6, decimal_places=1,
        null=True, blank=True,
        verbose_name="Écart mesuré/attendu (%)"
    )
    biogaz_cuisson_m3 = models.DecimalField(
        max_digits=9, decimal_places=2,
        null=True, blank=True,
        verbose_name="Biogaz cuisson (m³)"
    )
    biogaz_perte_m3 = models.DecimalField(
        max_digits=9, decimal_places=2,
        null=True, blank=True,
        verbose_name="Biogaz pertes (m³)"
    )
    biogaz_valorise_m3 = models.DecimalField(
        max_digits=9, decimal_places=2,
        null=True, blank=True,
        verbose_name="Biogaz valorisé (m³)"
    )
    electricite_kwh = models.DecimalField(
        max_digits=9, decimal_places=2,
        null=True, blank=True,
        verbose_name="Électricité (kWh)"
    )
    chaleur_kwh = models.DecimalField(
        max_digits=9, decimal_places=2,
        null=True, blank=True,
        verbose_name="Chaleur (kWh)"
    )
    digestat_kg = models.DecimalField(
        max_digits=9, decimal_places=2,
        null=True, blank=True,
        verbose_name="Digestat produit (kg)"
    )
    destination_digestat = models.CharField(
        max_length=20,
        choices=DestinationDigestat.choices,
        null=True, blank=True,
        verbose_name="Destination du digestat"
    )
    foyers_equivalents = models.DecimalField(
        max_digits=8, decimal_places=2,
        null=True, blank=True,
        verbose_name="Foyers équivalents (électricité)"
    )
    foyers_cuisson = models.DecimalField(
        max_digits=8, decimal_places=2,
        null=True, blank=True,
        verbose_name="Foyers équivalents (cuisson)"
    )
    # JSON : {"biogaz_mesure_m3": "simule", "electricite_kwh": "estime", ...}
    statuts_donnees = models.JSONField(
        default=dict,
        verbose_name="Badges Mesuré / Estimé / Simulé par champ"
    )

    class Meta:
        db_table = 'energie_production'
        verbose_name = 'Production Énergie'
        verbose_name_plural = 'Productions Énergie'
        unique_together = [('site', 'date')]
        ordering = ['-date', 'site']

    def __str__(self):
        return f"Production {self.site.code} — {self.date} ({self.get_statut_journee_display()})"
