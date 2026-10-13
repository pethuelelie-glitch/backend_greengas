import uuid
from django.db import models


class Recompense(models.Model):
    """Récompense disponible dans le catalogue contre des GreenPoints"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=150, verbose_name="Nom de la récompense")
    description = models.TextField(verbose_name="Description")
    cout_points = models.PositiveIntegerField(verbose_name="Coût en GreenPoints")
    partenaire = models.CharField(max_length=150, verbose_name="Partenaire fournisseur")
    actif = models.BooleanField(default=True, verbose_name="Disponible au catalogue")

    class Meta:
        db_table = 'greenpoints_recompense'
        verbose_name = 'Récompense'
        verbose_name_plural = 'Récompenses'
        ordering = ['cout_points']

    def __str__(self):
        return f"{self.nom} ({self.cout_points} pts) — {self.partenaire}"


class Echange(models.Model):
    """Échange de GreenPoints contre une récompense par un citoyen"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    citoyen = models.ForeignKey(
        'comptes.Utilisateur',
        on_delete=models.PROTECT,
        related_name='echanges',
        verbose_name="Citoyen"
    )
    recompense = models.ForeignKey(
        Recompense,
        on_delete=models.PROTECT,
        related_name='echanges',
        verbose_name="Récompense"
    )
    # Figé au moment de l'échange (le prix peut changer ensuite)
    cout_points = models.PositiveIntegerField(verbose_name="Coût payé (figé à l'échange)")
    date = models.DateTimeField(auto_now_add=True, verbose_name="Date de l'échange")

    class Meta:
        db_table = 'greenpoints_echange'
        verbose_name = 'Échange'
        verbose_name_plural = 'Échanges'
        ordering = ['-date']

    def __str__(self):
        return f"{self.citoyen} ↔ {self.recompense.nom} (-{self.cout_points} pts)"
