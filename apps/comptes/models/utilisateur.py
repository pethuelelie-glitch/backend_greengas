import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone


class Role(models.TextChoices):
    CITOYEN = 'citoyen', 'Citoyen'
    COLLECTEUR = 'collecteur', 'Collecteur'
    OPERATEUR_TRI = 'operateur_tri', 'Opérateur de tri'
    RESPONSABLE_METHANISATION = 'responsable_methanisation', 'Responsable méthanisation'
    REFERENT = 'referent', 'Référent'
    ADMINISTRATEUR = 'administrateur', 'Administrateur'
    CAPTEUR = 'capteur', 'Capteur'


class StatutValidation(models.TextChoices):
    EN_ATTENTE = 'en_attente', 'En attente'
    VALIDE = 'valide', 'Validé'
    REFUSE = 'refuse', 'Refusé'


class UtilisateurManager(BaseUserManager):
    def create_user(self, telephone, nom, password=None, role=Role.CITOYEN, **extra_fields):
        if not telephone:
            raise ValueError("Le numéro de téléphone est obligatoire")
        if not nom:
            raise ValueError("Le nom est obligatoire")

        extra_fields.setdefault('actif', True)
        utilisateur = self.model(
            telephone=telephone,
            nom=nom,
            role=role,
            **extra_fields
        )
        if password:
            utilisateur.set_password(password)
        else:
            utilisateur.set_unusable_password()

        utilisateur.save(using=self._db)
        return utilisateur

    def create_superuser(self, telephone, nom, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', Role.ADMINISTRATEUR)
        extra_fields.setdefault('statut_validation', StatutValidation.VALIDE)
        extra_fields.setdefault('telephone_verifie', True)

        return self.create_user(telephone, nom, password=password, **extra_fields)


class Utilisateur(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=150, verbose_name="Nom complet")
    telephone = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="Téléphone (+225...)"
    )
    email = models.EmailField(blank=True, null=True, verbose_name="Email")
    role = models.CharField(
        max_length=30,
        choices=Role.choices,
        default=Role.CITOYEN,
        verbose_name="Rôle"
    )
    actif = models.BooleanField(default=True, verbose_name="Actif")
    is_staff = models.BooleanField(default=False, verbose_name="Accès admin")
    date_creation = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")

    # Rattachement à un bac (pour citoyen ou référent)
    bac = models.ForeignKey(
        'referentiel.Bac',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='utilisateurs',
        verbose_name="Bac rattaché"
    )

    # Spécifique au citoyen
    telephone_verifie = models.BooleanField(default=False, verbose_name="Téléphone vérifié")
    statut_validation = models.CharField(
        max_length=20,
        choices=StatutValidation.choices,
        default=StatutValidation.VALIDE,
        verbose_name="Statut de validation"
    )
    date_inscription = models.DateTimeField(null=True, blank=True, verbose_name="Date d'inscription")

    objects = UtilisateurManager()

    USERNAME_FIELD = 'telephone'
    REQUIRED_FIELDS = ['nom']

    class Meta:
        db_table = 'comptes_utilisateur'
        verbose_name = 'Utilisateur'
        verbose_name_plural = 'Utilisateurs'
        ordering = ['-date_creation']

    def __str__(self):
        return f"{self.nom} ({self.telephone}) - {self.get_role_display()}"

    @property
    def is_active(self):
        return self.actif

    @is_active.setter
    def is_active(self, value):
        self.actif = value
