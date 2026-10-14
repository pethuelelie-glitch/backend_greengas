import re
import json
import secrets
from django.db.models import F
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth import authenticate
from django.db import transaction
from apps.comptes.models import Utilisateur, Role, StatutValidation, CodeOTP
from apps.comptes.exceptions import (
    ConflitException,
    MetierException,
    CompteNonValideException,
    TelephoneDejaUtiliseException,
    EmailDejaUtiliseException,
)
from apps.referentiel.models import Bac


TELEPHONE_REGEX = r'^\+225[0-9]{10}$'


class ProfilCitoyenSerializer(serializers.ModelSerializer):
    bac_id = serializers.UUIDField(source='bac.id', read_only=True, allow_null=True)
    code_bac = serializers.CharField(source='bac.code', read_only=True, allow_null=True)
    telephone_verifie = serializers.SerializerMethodField()
    statut_validation = serializers.SerializerMethodField()

    class Meta:
        model = Utilisateur
        fields = ['bac_id', 'code_bac', 'telephone_verifie', 'statut_validation', 'date_inscription']

    def get_telephone_verifie(self, obj):
        return True

    def get_statut_validation(self, obj):
        return 'valide'


class UtilisateurSerializer(serializers.ModelSerializer):
    profil_citoyen = serializers.SerializerMethodField()

    class Meta:
        model = Utilisateur
        fields = [
            'id', 'nom', 'telephone', 'email', 'role',
            'actif', 'statut_validation', 'date_creation', 'profil_citoyen'
        ]
        read_only_fields = ['id', 'date_creation']

    def get_profil_citoyen(self, obj):
        if obj.role in [Role.CITOYEN, Role.REFERENT]:
            return ProfilCitoyenSerializer(obj).data
        return None


class ConnexionSerializer(serializers.Serializer):
    """
    POST /api/v1/auth/token/ — OpenAPI 1.3.0
    Identifiant au choix : téléphone ou e-mail (exactement un des deux, sinon 400 VALIDATION).
    L'e-mail est comparé sans tenir compte des majuscules.
    Identifiant inconnu ou mauvais mot de passe : 401 NON_AUTHENTIFIE.
    Compte du personnel en attente ou refusé, ou compte désactivé (actif = false) :
    403 COMPTE_NON_VALIDE, avec details.statut_validation ou details.actif = false.
    Le mot de passe est vérifié avant.
    """
    telephone = serializers.CharField(required=False, allow_null=True)
    email = serializers.EmailField(required=False, allow_null=True)
    mot_de_passe = serializers.CharField(required=False, write_only=True)
    password = serializers.CharField(required=False, write_only=True)

    def validate(self, attrs):
        telephone = attrs.get('telephone')
        email = attrs.get('email')
        password = attrs.get('mot_de_passe') or attrs.get('password')

        if not password:
            raise serializers.ValidationError({"mot_de_passe": ["Le mot de passe est obligatoire."]})

        has_tel = bool(telephone and str(telephone).strip())
        has_email = bool(email and str(email).strip())

        # Exactement un des deux
        if (has_tel and has_email) or (not has_tel and not has_email):
            raise serializers.ValidationError(
                {"identifiant": ["Vous devez fournir exactement un identifiant : téléphone ou e-mail."]}
            )

        user = None
        if has_tel:
            tel_clean = str(telephone).strip()
            user = Utilisateur.objects.filter(telephone=tel_clean).first()
        elif has_email:
            email_clean = str(email).strip().lower()
            user = Utilisateur.objects.filter(email__iexact=email_clean).first()

        # Vérifier d'abord l'existence et le mot de passe -> 401 si mauvais
        if not user or not user.check_password(password):
            raise AuthenticationFailed(detail="Identifiant ou mot de passe incorrect.")

        # Vérification statut de validation et statut d'activation (403 COMPTE_NON_VALIDE)
        from apps.comptes.utils import is_validation_personnel_active

        if user.statut_validation == StatutValidation.EN_ATTENTE:
            if is_validation_personnel_active():
                raise CompteNonValideException(
                    message="Votre compte attend la validation d'un administrateur.",
                    details={"statut_validation": "en_attente"}
                )

        if user.statut_validation == StatutValidation.REFUSE:
            raise CompteNonValideException(
                message="Votre demande d'accès a été refusée.",
                details={"statut_validation": "refuse"}
            )

        if not user.actif:
            raise CompteNonValideException(
                message="Ce compte est désactivé.",
                details={"actif": False}
            )

        attrs['user'] = user
        return attrs


class InscriptionCitoyenSerializer(serializers.Serializer):
    """
    POST /api/v1/auth/inscription/ — OpenAPI 1.3.0
    Depuis 1.3.0 : pas de code SMS ni de validation par un référent.
    Le compte est créé avec statut_validation = valide et telephone_verifie = true.
    Les jetons sont renvoyés comme à la connexion (201 Jetons).
    Le rôle est toujours fixé à citoyen par le serveur.
    """
    nom = serializers.CharField(max_length=150, required=True)
    telephone = serializers.CharField(max_length=20, required=True)
    mot_de_passe = serializers.CharField(min_length=8, write_only=True, required=True)
    code_bac = serializers.CharField(max_length=20, required=True)

    def validate_telephone(self, value):
        if not re.match(TELEPHONE_REGEX, value):
            raise serializers.ValidationError("Le numéro de téléphone doit respecter le format international (+225 suivi de 10 chiffres).")
        if Utilisateur.objects.filter(telephone=value).exists():
            raise TelephoneDejaUtiliseException(
                details={"telephone": ["Ce numéro de téléphone est déjà utilisé."]}
            )
        return value

    def validate_code_bac(self, value):
        try:
            bac = Bac.objects.get(code=value)
            return bac
        except Bac.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound(detail=f"Le bac avec le code '{value}' est introuvable.", code="INTROUVABLE")

    def create(self, validated_data):
        bac = validated_data['code_bac']
        utilisateur = Utilisateur.objects.create_user(
            telephone=validated_data['telephone'],
            nom=validated_data['nom'],
            password=validated_data['mot_de_passe'],
            role=Role.CITOYEN,
            bac=bac,
            statut_validation=StatutValidation.VALIDE,
            telephone_verifie=True,
            actif=True
        )
        return utilisateur


class InscriptionPersonnelSerializer(serializers.Serializer):
    """
    POST /api/v1/auth/inscription/personnel/ — OpenAPI 1.3.0
    Depuis 1.3.0 : le compte est créé avec statut_validation = en_attente et AUCUN jeton n'est émis.
    L'utilisateur ne peut pas se connecter (403 COMPTE_NON_VALIDE) tant qu'un administrateur n'a pas validé.
    Téléphone et e-mail sont obligatoires ; chacun est unique (409 TELEPHONE_DEJA_UTILISE ou EMAIL_DEJA_UTILISE).
    L'e-mail est enregistré en minuscules.
    Seuls les rôles operateur_tri et responsable_methanisation sont acceptés.
    """
    nom = serializers.CharField(max_length=150, required=True)
    telephone = serializers.CharField(max_length=20, required=True)
    email = serializers.EmailField(required=True)
    mot_de_passe = serializers.CharField(min_length=8, write_only=True, required=True)
    role = serializers.CharField(max_length=30, required=True)

    def validate_telephone(self, value):
        if not re.match(TELEPHONE_REGEX, value):
            raise serializers.ValidationError("Le numéro de téléphone doit respecter le format international (+225 suivi de 10 chiffres).")
        if Utilisateur.objects.filter(telephone=value).exists():
            raise TelephoneDejaUtiliseException(
                details={"telephone": ["Ce numéro de téléphone est déjà utilisé."]}
            )
        return value

    def validate_email(self, value):
        email_clean = value.strip().lower()
        if Utilisateur.objects.filter(email__iexact=email_clean).exists():
            raise EmailDejaUtiliseException(
                details={"email": ["Cette adresse e-mail est déjà utilisée."]}
            )
        return email_clean

    def validate_role(self, value):
        roles_autorises = [Role.OPERATEUR_TRI, Role.RESPONSABLE_METHANISATION]
        if value not in roles_autorises:
            raise serializers.ValidationError("Le rôle doit être 'operateur_tri' ou 'responsable_methanisation'.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        from apps.comptes.utils import is_validation_personnel_active

        val_active = is_validation_personnel_active()
        statut_val = StatutValidation.EN_ATTENTE if val_active else StatutValidation.VALIDE

        utilisateur = Utilisateur.objects.create_user(
            telephone=validated_data['telephone'],
            email=validated_data['email'].strip().lower(),
            nom=validated_data['nom'],
            password=validated_data['mot_de_passe'],
            role=validated_data['role'],
            statut_validation=statut_val,
            actif=True,
            telephone_verifie=True
        )

        from apps.supervision.models import JournalAudit, TypeObjet
        en_attente = statut_val == StatutValidation.EN_ATTENTE
        JournalAudit.objects.create(
            auteur=utilisateur,
            action="utilisateur.demande_inscription" if en_attente else "utilisateur.inscrire",
            objet_type=TypeObjet.UTILISATEUR,
            objet_id=str(utilisateur.id),
            nouvelle_valeur=json.dumps({
                "nom": utilisateur.nom,
                "telephone": utilisateur.telephone,
                "email": utilisateur.email,
                "role": utilisateur.role,
                "statut_validation": statut_val
            }),
            motif=(
                "Demande d'inscription personnel en attente de validation admin"
                if en_attente else "Inscription personnel"
            )
        )

        return utilisateur


class OtpVerificationSerializer(serializers.Serializer):
    telephone = serializers.CharField(required=True)
    code = serializers.CharField(max_length=6, min_length=6, required=True)

    def validate(self, attrs):
        telephone = attrs.get('telephone')
        code = attrs.get('code')

        otp = CodeOTP.objects.filter(telephone=telephone, utilise=False).order_by('-cree_le').first()
        if not otp:
            raise MetierException(
                code="OTP_INVALIDE",
                message="Code OTP invalide",
                details={"code": ["Code OTP invalide."]}
            )
        if otp.est_expire:
            raise MetierException(
                code="OTP_EXPIRE",
                message="Ce code OTP a expiré",
                details={"code": ["Ce code OTP a expiré."]}
            )

        if otp.tentatives >= CodeOTP.MAX_TENTATIVES:
            raise MetierException(
                code="OTP_INVALIDE",
                message="Le nombre maximal de tentatives est atteint. Demandez un nouveau code.",
                details={"code": ["Le nombre maximal de tentatives est atteint."]}
            )

        if not secrets.compare_digest(otp.code, code):
            CodeOTP.objects.filter(
                pk=otp.pk,
                utilise=False,
                tentatives__lt=CodeOTP.MAX_TENTATIVES,
            ).update(tentatives=F('tentatives') + 1)
            raise MetierException(
                code="OTP_INVALIDE",
                message="Code OTP invalide",
                details={"code": ["Code OTP invalide."]}
            )

        attrs['otp'] = otp
        return attrs


class CustomTokenRefreshSerializer(serializers.Serializer):
    """
    Rafraîchissement de token JWT.
    Vérifie que le compte n'est pas en attente, refusé ou inactif (403 COMPTE_NON_VALIDE).
    """
    refresh = serializers.CharField()

    def validate(self, attrs):
        from rest_framework_simplejwt.tokens import RefreshToken
        from rest_framework_simplejwt.exceptions import TokenError

        refresh_str = attrs.get('refresh')
        try:
            refresh = RefreshToken(refresh_str)
        except TokenError as e:
            raise AuthenticationFailed(detail=str(e))

        user_id = refresh.payload.get('user_id')
        user = Utilisateur.objects.filter(id=user_id).first()

        if not user:
            raise AuthenticationFailed(detail="Le compte associé à ce jeton n'existe plus.")

        from apps.comptes.utils import is_validation_personnel_active

        if user.statut_validation == StatutValidation.EN_ATTENTE:
            if is_validation_personnel_active():
                raise CompteNonValideException(
                    message="Votre compte attend la validation d'un administrateur.",
                    details={"statut_validation": "en_attente"}
                )

        if user.statut_validation == StatutValidation.REFUSE:
            raise CompteNonValideException(
                message="Votre demande d'accès a été refusée.",
                details={"statut_validation": "refuse"}
            )

        if not user.actif:
            raise CompteNonValideException(
                message="Ce compte est désactivé.",
                details={"actif": False}
            )

        data = {'access': str(refresh.access_token)}
        from rest_framework_simplejwt.settings import api_settings
        if api_settings.ROTATE_REFRESH_TOKENS:
            if api_settings.BLACKLIST_AFTER_ROTATION:
                refresh.blacklist()
            refresh.set_jti()
            refresh.set_exp()
            refresh.set_iat()
            data['refresh'] = str(refresh)
        return data


class TokenRevokeSerializer(serializers.Serializer):
    """Révoque un refresh token appartenant à l'utilisateur authentifié."""
    refresh = serializers.CharField()

    def validate(self, attrs):
        from rest_framework_simplejwt.tokens import RefreshToken
        from rest_framework_simplejwt.exceptions import TokenError

        try:
            token = RefreshToken(attrs['refresh'])
        except TokenError as exc:
            raise AuthenticationFailed(detail="Le jeton de renouvellement est invalide ou révoqué.") from exc

        request = self.context['request']
        if str(token.payload.get('user_id')) != str(request.user.id):
            raise AuthenticationFailed(detail="Ce jeton n'appartient pas à l'utilisateur connecté.")

        token.blacklist()
        return {}
