from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from django.utils import timezone

from apps.comptes.models import Utilisateur, CodeOTP, Role, StatutValidation
from apps.comptes.permissions import EstAdmin
from apps.comptes.serializers import (
    UtilisateurSerializer,
    ConnexionSerializer,
    InscriptionCitoyenSerializer,
    OtpVerificationSerializer,
)


class ConnexionView(APIView):
    """
    POST /api/v1/auth/token/
    Connexion par téléphone et mot de passe.
    Renvoie les tokens JWT et le profil utilisateur avec son rôle.
    """
    permission_classes = [AllowAny]
    throttle_scope = 'auth_login'

    def post(self, request):
        serializer = ConnexionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)

        # Injecter le rôle dans le token JWT
        refresh['role'] = user.role
        refresh['nom'] = user.nom

        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "utilisateur": UtilisateurSerializer(user).data
        }, status=status.HTTP_200_OK)


class MoiView(APIView):
    """
    GET /api/v1/auth/moi/
    Renvoie le profil de l'utilisateur actuellement connecté.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UtilisateurSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class InscriptionCitoyenView(APIView):
    """
    POST /api/v1/auth/inscription/ — OpenAPI 1.3.0
    Inscription citoyen libre. Compte actif aussitôt et connecté (renvoie les Jetons 201).
    Pas de SMS OTP ni de validation référent requis.
    """
    permission_classes = [AllowAny]
    throttle_scope = 'auth_registration'

    def post(self, request):
        serializer = InscriptionCitoyenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        utilisateur = serializer.save()

        # Émettre les jetons JWT immédiatement
        refresh = RefreshToken.for_user(utilisateur)
        refresh['role'] = utilisateur.role
        refresh['nom'] = utilisateur.nom

        # Notification bac_surinscrit si le bac dépasse ses foyers déclarés (Contrat 1.4.0)
        try:
            if utilisateur.bac:
                bac = utilisateur.bac
                nb_citoyens = Utilisateur.objects.filter(bac=bac, role=Role.CITOYEN, actif=True).count()
                if bac.nb_foyers_declares and nb_citoyens > bac.nb_foyers_declares:
                    from apps.supervision.models import TypeNotification, NiveauNotification
                    from apps.supervision.services import notifier_utilisateurs
                    admins = list(Utilisateur.objects.filter(role=Role.ADMINISTRATEUR, actif=True))
                    referents = list(Utilisateur.objects.filter(bac=bac, role=Role.REFERENT, actif=True))
                    dest = list({u.id: u for u in (admins + referents)}.values())
                    notifier_utilisateurs(
                        destinataires=dest,
                        type=TypeNotification.BAC_SURINSCRIT,
                        niveau=NiveauNotification.INFO,
                        titre="Bac surinscrit",
                        message=f"{bac.code} : {nb_citoyens} comptes pour {bac.nb_foyers_declares} foyers.",
                        objet_type="bac",
                        objet_id=bac.id
                    )
        except Exception:
            pass

        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "utilisateur": UtilisateurSerializer(utilisateur).data
        }, status=status.HTTP_201_CREATED)


class InscriptionPersonnelView(APIView):
    """
    POST /api/v1/auth/inscription/personnel/ — OpenAPI 1.3.0
    Inscription d'un opérateur de tri ou d'un responsable méthanisation (Control Center).
    Le compte est créé avec statut_validation = en_attente et AUCUN jeton n'est émis.
    Renvoie 201 avec le profil Utilisateur en attente de validation admin.
    """
    throttle_scope = 'auth_registration'

    def get_permissions(self):
        # Les candidatures publiques ne sont permises que si elles seront soumises
        # à validation. Sans validation, seul un administrateur peut créer le compte.
        from apps.comptes.utils import is_validation_personnel_active
        if is_validation_personnel_active():
            return [AllowAny()]
        return [IsAuthenticated(), EstAdmin()]

    def post(self, request):
        from apps.comptes.serializers import InscriptionPersonnelSerializer
        serializer = InscriptionPersonnelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        utilisateur = serializer.save()

        # Notification compte_a_valider à tous les administrateurs (Contrat 1.4.0 & 1.5.0)
        # Uniquement si validation_comptes_personnel == 1 et compte en attente
        from apps.comptes.utils import is_validation_personnel_active
        if is_validation_personnel_active() and utilisateur.statut_validation == StatutValidation.EN_ATTENTE:
            try:
                from apps.supervision.models import TypeNotification, NiveauNotification
                from apps.supervision.services import notifier_utilisateurs
                admins = Utilisateur.objects.filter(role=Role.ADMINISTRATEUR, actif=True)
                role_label = dict(Role.choices).get(utilisateur.role, utilisateur.role).lower()
                notifier_utilisateurs(
                    destinataires=admins,
                    type=TypeNotification.COMPTE_A_VALIDER,
                    niveau=NiveauNotification.ATTENTION,
                    titre="Compte à valider",
                    message=f"{utilisateur.nom} demande un accès {role_label}.",
                    objet_type="utilisateur",
                    objet_id=utilisateur.id
                )
            except Exception:
                pass

        return Response(
            UtilisateurSerializer(utilisateur).data,
            status=status.HTTP_201_CREATED
        )


class OtpVerifierView(APIView):
    """
    POST /api/v1/auth/otp/verifier/
    Validation du code OTP reçu par SMS.
    """
    permission_classes = [AllowAny]
    throttle_scope = 'auth_otp_verify'

    def post(self, request):
        serializer = OtpVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        otp = serializer.validated_data['otp']
        claimed = CodeOTP.objects.filter(
            pk=otp.pk,
            utilise=False,
            tentatives__lt=CodeOTP.MAX_TENTATIVES,
            expire_le__gt=timezone.now(),
        ).update(utilise=True)
        if not claimed:
            return Response(
                {"code": "OTP_INVALIDE", "message": "Ce code OTP n'est plus valide", "details": {}},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        # Validation du téléphone de l'utilisateur
        utilisateur = Utilisateur.objects.filter(telephone=otp.telephone).first()
        if utilisateur:
            utilisateur.telephone_verifie = True
            utilisateur.save()
            return Response(UtilisateurSerializer(utilisateur).data, status=status.HTTP_200_OK)

        return Response(
            {"code": "INTROUVABLE", "message": "Utilisateur introuvable", "details": {}},
            status=status.HTTP_404_NOT_FOUND
        )


class OtpRenvoyerView(APIView):
    """
    POST /api/v1/auth/otp/renvoyer/
    Renvoi d'un nouveau code OTP.
    """
    permission_classes = [AllowAny]
    throttle_scope = 'auth_otp_resend'

    def post(self, request):
        telephone = request.data.get('telephone')
        if not telephone:
            return Response(
                {"code": "VALIDATION", "message": "Le champ téléphone est requis", "details": {}},
                status=status.HTTP_400_BAD_REQUEST
            )

        utilisateur = Utilisateur.objects.filter(telephone=telephone).first()
        if not utilisateur:
            return Response(
                {"code": "INTROUVABLE", "message": "Aucun compte associé à ce numéro", "details": {}},
                status=status.HTTP_404_NOT_FOUND
            )

        CodeOTP.generer_code(telephone)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CustomTokenRefreshView(APIView):
    """
    POST /api/v1/auth/token/rafraichir/
    Rafraîchissement de token JWT.
    Refuse les comptes en attente, refusés ou inactifs (403 COMPTE_NON_VALIDE).
    """
    permission_classes = [AllowAny]
    throttle_scope = 'auth_refresh'

    def post(self, request):
        from apps.comptes.serializers import CustomTokenRefreshSerializer
        serializer = CustomTokenRefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class TokenRevokeView(APIView):
    """Révoque le refresh token de l'utilisateur connecté."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.comptes.serializers import TokenRevokeSerializer

        serializer = TokenRevokeSerializer(
            data=request.data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        return Response(status=status.HTTP_204_NO_CONTENT)
