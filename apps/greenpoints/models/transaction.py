import uuid
from django.db import models


class StatutTransaction(models.TextChoices):
    CREDITEE = 'creditee', 'Créditée'
    EN_ATTENTE = 'en_attente', 'En attente'
    ANNULEE = 'annulee', 'Annulée'


class GreenPointsTransaction(models.Model):
    """Distribution de points GreenPoints à un citoyen suite à un tri"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    citoyen = models.ForeignKey(
        'comptes.Utilisateur',
        on_delete=models.PROTECT,
        related_name='transactions_points',
        verbose_name="Citoyen"
    )
    bac = models.ForeignKey(
        'referentiel.Bac',
        on_delete=models.PROTECT,
        related_name='transactions_points',
        verbose_name="Bac"
    )
    tournee = models.ForeignKey(
        'collecte.Tournee',
        on_delete=models.PROTECT,
        related_name='transactions_points',
        verbose_name="Tournée"
    )
    collecte = models.ForeignKey(
        'collecte.Collecte',
        on_delete=models.PROTECT,
        related_name='transactions_points',
        verbose_name="Collecte"
    )

    # Détail du calcul (figé au moment de la création)
    scans_citoyen = models.PositiveIntegerField(verbose_name="Scans du citoyen sur la période")
    scans_bac = models.PositiveIntegerField(verbose_name="Scans totaux du bac sur la période")
    poids_attribue_kg = models.DecimalField(
        max_digits=7, decimal_places=2,
        verbose_name="Poids attribué au citoyen (kg)"
    )
    valeur_kg = models.DecimalField(
        max_digits=6, decimal_places=4,
        verbose_name="Valeur au kilo de la tournée (points/kg)"
    )
    coef_qualite = models.DecimalField(
        max_digits=4, decimal_places=2,
        verbose_name="Coefficient de qualité appliqué"
    )
    points = models.PositiveIntegerField(verbose_name="Points attribués (entier inférieur)")
    statut = models.CharField(
        max_length=15,
        choices=StatutTransaction.choices,
        default=StatutTransaction.EN_ATTENTE,
        verbose_name="Statut"
    )
    date = models.DateTimeField(auto_now_add=True, verbose_name="Date de la transaction")

    class Meta:
        db_table = 'greenpoints_transaction'
        verbose_name = 'Transaction GreenPoints'
        verbose_name_plural = 'Transactions GreenPoints'
        ordering = ['-date']

    def __str__(self):
        return f"+{self.points} pts → {self.citoyen} [{self.get_statut_display()}]"
