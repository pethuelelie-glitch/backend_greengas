import uuid
import secrets
from datetime import timedelta
from django.db import models
from django.utils import timezone


class CodeOTP(models.Model):
    """Code OTP à 6 chiffres envoyé par SMS pour validation du numéro de téléphone"""
    MAX_TENTATIVES = 5
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    telephone = models.CharField(max_length=20, verbose_name="Numéro de téléphone")
    code = models.CharField(max_length=6, verbose_name="Code OTP")
    cree_le = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    expire_le = models.DateTimeField(verbose_name="Expire le")
    utilise = models.BooleanField(default=False, verbose_name="Utilisé")
    tentatives = models.PositiveSmallIntegerField(default=0, verbose_name="Tentatives de vérification")

    class Meta:
        db_table = 'comptes_code_otp'
        verbose_name = 'Code OTP'
        verbose_name_plural = 'Codes OTP'
        ordering = ['-cree_le']

    def __str__(self):
        return f"OTP pour {self.telephone} ({'Utilisé' if self.utilise else 'En attente'})"

    @property
    def est_expire(self):
        return timezone.now() > self.expire_le

    @classmethod
    def generer_code(cls, telephone):
        """Génère un code OTP valide 10 minutes"""
        # Invalidation des anciens codes non utilisés pour ce numéro
        cls.objects.filter(telephone=telephone, utilise=False).update(utilise=True)

        code = f"{secrets.randbelow(900000) + 100000:06d}"
        expire_le = timezone.now() + timedelta(minutes=10)

        return cls.objects.create(
            telephone=telephone,
            code=code,
            expire_le=expire_le,
            utilise=False
        )
