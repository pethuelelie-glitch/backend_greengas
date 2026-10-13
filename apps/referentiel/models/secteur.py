import uuid
from django.db import models


class CodeSecteur(models.TextChoices):
    NORD = 'NORD', 'NORD'
    EST = 'EST', 'EST'
    OUEST = 'OUEST', 'OUEST'


class Secteur(models.Model):
    """Secteur géographique de collecte"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=10, choices=CodeSecteur.choices, unique=True, verbose_name="Code secteur")
    nom = models.CharField(max_length=150, verbose_name="Nom du secteur")
    site = models.ForeignKey(
        'referentiel.Site',
        on_delete=models.PROTECT,
        related_name='secteurs_normaux',
        verbose_name="Site digesteur normal"
    )
    site_repli = models.ForeignKey(
        'referentiel.Site',
        on_delete=models.PROTECT,
        related_name='secteurs_repli',
        verbose_name="Site de repli"
    )

    class Meta:
        db_table = 'referentiel_secteur'
        verbose_name = 'Secteur'
        verbose_name_plural = 'Secteurs'

    def __str__(self):
        return f"{self.code} - {self.nom}"
