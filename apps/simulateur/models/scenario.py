import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class ScenarioSimulation(models.Model):
    """
    Scénario de démonstration / simulation permettant de forcer le facteur de mesure d'un site.
    Exemple : 0.70 pour simuler une baisse de biogaz de 30 % et déclencher une alerte.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.OneToOneField(
        'referentiel.Site',
        on_delete=models.CASCADE,
        related_name='scenario_simulation',
        verbose_name="Site digesteur"
    )
    facteur_mesure = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(2)],
        verbose_name="Facteur de mesure"
    )
    date_creation = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    date_modification = models.DateTimeField(auto_now=True, verbose_name="Date de modification")

    class Meta:
        db_table = 'simulateur_scenario'
        verbose_name = 'Scénario de simulation'
        verbose_name_plural = 'Scénarios de simulation'
        ordering = ['site__code']

    def __str__(self):
        return f"Scénario {self.site.code} (facteur: {self.facteur_mesure})"
