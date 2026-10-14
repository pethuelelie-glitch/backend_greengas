import re
import json
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import authenticate
from django.db import transaction
from apps.comptes.models import Utilisateur, Role, StatutValidation, CodeOTP
from apps.comptes.exceptions import ConflitException, MetierException
from apps.referentiel.models import Bac


TELEPHONE_REGEX = r'^\+225[0-9]{10}$'


class ProfilCitoyenSerializer(serializers.ModelSerializer):
    bac_id = serializers.UUIDField(source='bac.id', read_only=True, allow_null=True)
    code_bac = serializers.CharField(source='bac.code', read_only=True, allow_null=True)

    class Meta:
        model = Utilisateur
        fields = ['bac_id', 'code_bac', 'telephone_verifie', 'statut_validation', 'date_inscription']


class UtilisateurSerializer(serializers.ModelSerializer):
    profil_citoyen = serializers.SerializerMethodField()

    class Meta:
        model = Utilisateur
        fields = [
            'id', 'nom', 'telephone', 'email', 'role',
            'actif', 'date_creation', 'profil_citoyen'
        ]
        read_only_fields = ['id', 'date_creation']

    def get_profil_citoyen(self, obj):
        if obj.role in [Role.CITOYEN, Role.REFERENT]:
            return ProfilCitoyenSerializer(obj).data
        return None


class ConnexionSerializer(serializers.Serializer):
    """
    Connexion par numéro de téléphone et mot de passe.
    Supporte à la fois 'mot_de_passe' et 'password'.
    """
    telephone = serializers.CharField(required=True)
    mot_de_passe = serializers.CharField(required=False, write_only=True)
    password = serializers.CharField(required=False, write_only=True)

    def validate(self, attrs):
        telephone = attrs.get('telephone')
        password = attrs.get('mot_de_passe') or attrs.get('password')

        if not password:
            raise serializers.ValidationError({"mot_de_passe": ["Le mot de passe est obligatoire."]})

        user = authenticate(username=telephone, password=password)
        if not user:
            # Fallback direct lookup
            u = Utilisateur.objects.filter(telephone=telephone).first()
            if u and u.check_password(password):
                user = u

        if not user:
            raise serializers.ValidationError({"non_field_errors": ["Numéro de téléphone ou mot de passe incorrect."]})

        if not user.actif:
            raise serializers.ValidationError({"non_field_errors": ["Ce compte a été désactivé."]})

        attrs['user'] = user
        return attrs


class InscriptionCitoyenSerializer(serializers.Serializer):
    """Inscription citoyen (envoie un code OTP par SMS)"""
    nom = serializers.CharField(max_length=150, required=True)
    telephone = serializers.CharField(max_length=20, required=True)
    mot_de_passe = serializers.CharField(min_length=8, write_only=True, required=True)
    code_bac = serializers.CharField(max_length=20, required=True)

    def validate_telephone(self, value):
        if not re.match(TELEPHONE_REGEX, value):
            raise serializers.ValidationError("Le numéro de téléphone doit respecter le format international (+225 suivi de 10 chiffres).")
        if Utilisateur.objects.filter(telephone=value).exists():
            raise ConflitException(
                code="TELEPHONE_DEJA_UTILISE",
                message="Ce numéro de téléphone est déjà associé à un compte",
                details={"telephone": ["Ce numéro de téléphone est déjà utilisé."]}
            )
        return value

    def validate_code_bac(self, value):
        try:
            bac = Bac.objects.get(code=value)
            return bac
        except Bac.DoesNotExist:
            raise serializers.ValidationError(f"Le bac avec le code '{value}' est introuvable.")

    def create(self, validated_data):
        bac = validated_data['code_bac']
        utilisateur = Utilisateur.objects.create_user(
            telephone=validated_data['telephone'],
            nom=validated_data['nom'],
            password=validated_data['mot_de_passe'],
            role=Role.CITOYEN,
            bac=bac,
            statut_validation=StatutValidation.EN_ATTENTE,
            telephone_verifie=False
        )
        # Génération du code OTP
        CodeOTP.generer_code(utilisateur.telephone)
        return utilisateur


class InscriptionPersonnelSerializer(serializers.Serializer):
    """
    Inscription d'un opérateur de tri ou d'un responsable méthanisation (Control Center).
    Contrat 1.1.0 — Créé actif immédiatement, émet des jetons JWT.
    """
    nom = serializers.CharField(max_length=150, required=True)
    telephone = serializers.CharField(max_length=20, required=True)
    mot_de_passe = serializers.CharField(min_length=8, write_only=True, required=True)
    role = serializers.CharField(max_length=30, required=True)

    def validate_telephone(self, value):
        if not re.match(TELEPHONE_REGEX, value):
            raise serializers.ValidationError("Le numéro de téléphone doit respecter le format international (+225 suivi de 10 chiffres).")
        if Utilisateur.objects.filter(telephone=value).exists():
            raise ConflitException(
                code="TELEPHONE_DEJA_UTILISE",
                message="Ce numéro de téléphone est déjà associé à un compte",
                details={"telephone": ["Ce numéro de téléphone est déjà utilisé."]}
            )
        return value

    def validate_role(self, value):
        roles_autorises = [Role.OPERATEUR_TRI, Role.RESPONSABLE_METHANISATION]
        if value not in roles_autorises:
            raise serializers.ValidationError("Le rôle doit être 'operateur_tri' ou 'responsable_methanisation'.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        utilisateur = Utilisateur.objects.create_user(
            telephone=validated_data['telephone'],
            nom=validated_data['nom'],
            password=validated_data['mot_de_passe'],
            role=validated_data['role'],
            actif=True,
            telephone_verifie=True
        )

        # Journaliser l'inscription dans JournalAudit
        from apps.supervision.models import JournalAudit, TypeObjet
        JournalAudit.objects.create(
            auteur=utilisateur,
            action="utilisateur.inscrire",
            objet_type=TypeObjet.UTILISATEUR,
            objet_id=str(utilisateur.id),
            nouvelle_valeur=json.dumps({
                "nom": utilisateur.nom,
                "telephone": utilisateur.telephone,
                "role": utilisateur.role
            }),
            motif="Inscription personnel via Control Center"
        )

        return utilisateur


class OtpVerificationSerializer(serializers.Serializer):
    telephone = serializers.CharField(required=True)
    code = serializers.CharField(max_length=6, min_length=6, required=True)

    def validate(self, attrs):
        telephone = attrs.get('telephone')
        code = attrs.get('code')

        otp = CodeOTP.objects.filter(telephone=telephone, code=code, utilise=False).first()
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

        attrs['otp'] = otp
        return attrs

