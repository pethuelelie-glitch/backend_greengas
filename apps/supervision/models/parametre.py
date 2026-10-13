from django.db import models
from django.utils import timezone


class StatutParametre(models.TextChoices):
    ALIGNE = 'aligne', 'Aligné (source vérifiée)'
    ILLUSTRATIF = 'illustratif', 'Illustratif'
    A_SOURCER = 'a_sourcer', 'À sourcer'
    A_CALIBRER = 'a_calibrer', 'À calibrer'
    V2 = 'v2', 'Prévu en V2'


class Parametre(models.Model):
    """
    Paramètre système éditable par l'administrateur sans redéploiement.
    La clé (cle) sert de clé primaire lisible, ex: 'coefficient_filiere_organique'.
    """
    cle = models.CharField(
        max_length=80, primary_key=True,
        verbose_name="Clé du paramètre"
    )
    valeur = models.DecimalField(
        max_digits=12, decimal_places=4,
        verbose_name="Valeur"
    )
    unite = models.CharField(max_length=30, verbose_name="Unité")
    statut = models.CharField(
        max_length=15,
        choices=StatutParametre.choices,
        default=StatutParametre.ALIGNE,
        verbose_name="Statut de la valeur"
    )
    description = models.TextField(verbose_name="Description du paramètre")
    source = models.TextField(
        blank=True, null=True,
        verbose_name="Source / référence"
    )
    date_modification = models.DateTimeField(
        default=timezone.now,
        verbose_name="Dernière modification"
    )

    class Meta:
        db_table = 'supervision_parametre'
        verbose_name = 'Paramètre système'
        verbose_name_plural = 'Paramètres système'
        ordering = ['cle']

    def __str__(self):
        return f"{self.cle} = {self.valeur} {self.unite}"
