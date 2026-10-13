import uuid
from django.db import models


class TypeAlerte(models.TextChoices):
    PRODUCTION = 'production', 'Écart de production biogaz'
    COMPOSITION = 'composition', 'Composition du biogaz (CH₄)'


class StatutAlerte(models.TextChoices):
    OUVERTE = 'ouverte', 'Ouverte'
    RESOLUE = 'resolue', 'Résolue'


class Alerte(models.Model):
    """Alerte de performance sur un site méthaniseur"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.ForeignKey(
        'referentiel.Site',
        on_delete=models.PROTECT,
        related_name='alertes',
        verbose_name="Site digesteur"
    )
    type = models.CharField(
        max_length=15,
        choices=TypeAlerte.choices,
        verbose_name="Type d'alerte"
    )
    statut = models.CharField(
        max_length=10,
        choices=StatutAlerte.choices,
        default=StatutAlerte.OUVERTE,
        verbose_name="Statut"
    )

    # Valeurs à l'origine de l'alerte
    valeur_attendue = models.DecimalField(
        max_digits=9, decimal_places=2,
        verbose_name="Valeur attendue (m³ ou % CH₄)"
    )
    valeur_mesuree = models.DecimalField(
        max_digits=9, decimal_places=2,
        verbose_name="Valeur mesurée"
    )
    ecart_pct = models.DecimalField(
        max_digits=6, decimal_places=1,
        verbose_name="Écart (%)"
    )
    description = models.TextField(verbose_name="Description de l'alerte")

    # Regroupement des occurrences consécutives
    nb_occurrences = models.PositiveIntegerField(
        default=1,
        verbose_name="Nombre de jours regroupés"
    )

    # Horodatages
    date_creation = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    date_derniere_occurrence = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de la dernière occurrence"
    )
    date_resolution = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Date de résolution"
    )

    # Résolution
    commentaire_resolution = models.TextField(
        null=True, blank=True,
        verbose_name="Commentaire de résolution (obligatoire)"
    )
    resolue_par = models.ForeignKey(
        'comptes.Utilisateur',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='alertes_resolues',
        verbose_name="Résolu par"
    )

    class Meta:
        db_table = 'energie_alerte'
        verbose_name = 'Alerte'
        verbose_name_plural = 'Alertes'
        ordering = ['-date_creation']

    def __str__(self):
        return f"Alerte {self.get_type_display()} — {self.site.code} [{self.get_statut_display()}]"
