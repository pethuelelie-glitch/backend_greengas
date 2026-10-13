import uuid
from django.db import models


class Categorie(models.TextChoices):
    ORGANIQUE = 'organique', 'Organique'
    BIOMASSE = 'biomasse', 'Biomasse'
    PLASTIQUE = 'plastique', 'Plastique'
    METAL = 'metal', 'Métal'
    CARTON_PAPIER = 'carton_papier', 'Carton / Papier'
    VERRE = 'verre', 'Verre'
    REFUS = 'refus', 'Refus'


class Destination(models.TextChoices):
    DIGESTEUR = 'digesteur', 'Digesteur (méthanisation)'
    UNITE_BIOMASSE = 'unite_biomasse', 'Unité biomasse'
    RECYCLEUR = 'recycleur', 'Recycleur'
    ENFOUISSEMENT = 'enfouissement', 'Enfouissement'


# Correspondance catégorie → destination (règle figée dans le guide)
DESTINATION_PAR_CATEGORIE = {
    Categorie.ORGANIQUE: Destination.DIGESTEUR,
    Categorie.BIOMASSE: Destination.UNITE_BIOMASSE,
    Categorie.PLASTIQUE: Destination.RECYCLEUR,
    Categorie.METAL: Destination.RECYCLEUR,
    Categorie.CARTON_PAPIER: Destination.RECYCLEUR,
    Categorie.VERRE: Destination.RECYCLEUR,
    Categorie.REFUS: Destination.ENFOUISSEMENT,
}


class LotTrie(models.Model):
    """Lot de matière trié par catégorie, issu d'une tournée"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code_lot = models.CharField(
        max_length=20, unique=True,
        verbose_name="Code lot (ex: ORG-0258)"
    )
    tournee = models.ForeignKey(
        'collecte.Tournee',
        on_delete=models.PROTECT,
        related_name='lots',
        verbose_name="Tournée"
    )
    categorie = models.CharField(
        max_length=20,
        choices=Categorie.choices,
        verbose_name="Catégorie de matière"
    )
    poids_kg = models.DecimalField(
        max_digits=8, decimal_places=2,
        verbose_name="Poids du lot (kg)"
    )
    # Champs calculés par le backend
    part_pct = models.DecimalField(
        max_digits=5, decimal_places=2,
        verbose_name="Part dans la tournée (%)"
    )
    destination = models.CharField(
        max_length=20,
        choices=Destination.choices,
        verbose_name="Destination"
    )
    # Renseigné uniquement pour la catégorie organique
    site = models.ForeignKey(
        'referentiel.Site',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='lots_organiques',
        verbose_name="Site digesteur de destination"
    )

    class Meta:
        db_table = 'tri_lot_trie'
        verbose_name = 'Lot trié'
        verbose_name_plural = 'Lots triés'
        unique_together = [('tournee', 'categorie')]  # Une catégorie par tournée
        ordering = ['tournee', 'categorie']

    def __str__(self):
        return f"{self.code_lot} — {self.get_categorie_display()} ({self.poids_kg} kg)"
