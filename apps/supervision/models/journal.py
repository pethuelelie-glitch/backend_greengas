import uuid
from django.db import models


class TypeObjet(models.TextChoices):
    UTILISATEUR = 'utilisateur', 'Utilisateur'
    BAC = 'bac', 'Bac'
    SCAN = 'scan', 'Scan'
    SECTEUR = 'secteur', 'Secteur'
    SITE = 'site', 'Site'
    TOURNEE = 'tournee', 'Tournée'
    COLLECTE = 'collecte', 'Collecte'
    LOT = 'lot', 'Lot'
    LOT_TRIE = 'lot_trie', 'Lot trié'
    TRANSACTION = 'transaction', 'Transaction GreenPoints'
    RECOMPENSE = 'recompense', 'Récompense'
    ECHANGE = 'echange', 'Échange'
    PRODUCTION = 'production', 'Production énergie'
    ALERTE = 'alerte', 'Alerte'
    PARAMETRE = 'parametre', 'Paramètre'


class JournalAudit(models.Model):
    """
    Journal immuable de toutes les actions administratives sensibles.
    Chaque action est enregistrée avec l'état avant et après.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    date = models.DateTimeField(auto_now_add=True, verbose_name="Date de l'action")
    auteur = models.ForeignKey(
        'comptes.Utilisateur',
        on_delete=models.PROTECT,
        related_name='actions_audit',
        verbose_name="Auteur de l'action"
    )
    # Exemple : "parametre.modifier", "collecte.decider", "alerte.resoudre"
    action = models.CharField(max_length=60, verbose_name="Action effectuée")
    objet_type = models.CharField(
        max_length=20,
        choices=TypeObjet.choices,
        verbose_name="Type d'objet concerné"
    )
    objet_id = models.CharField(
        max_length=80,
        verbose_name="Identifiant de l'objet concerné"
    )
    # Valeurs sérialisées en JSON string (ex: '"0.1"', '{"statut": "nominal"}')
    ancienne_valeur = models.TextField(
        null=True, blank=True,
        verbose_name="Ancienne valeur (JSON)"
    )
    nouvelle_valeur = models.TextField(
        null=True, blank=True,
        verbose_name="Nouvelle valeur (JSON)"
    )
    motif = models.TextField(
        null=True, blank=True,
        verbose_name="Motif de la décision"
    )

    class Meta:
        db_table = 'supervision_journal_audit'
        verbose_name = "Entrée du journal d'audit"
        verbose_name_plural = "Journal d'audit"
        ordering = ['-date']

    def __str__(self):
        return f"{self.date:%Y-%m-%d %H:%M} | {self.auteur} | {self.action} | {self.objet_type}:{self.objet_id}"
