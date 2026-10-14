from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from apps.comptes.models import Utilisateur, CodeOTP
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
    POST /api/v1/auth/inscription/
    Inscription citoyen libre et envoi d'un code OTP par SMS.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = InscriptionCitoyenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        utilisateur = serializer.save()

        return Response(
            UtilisateurSerializer(utilisateur).data,
            status=status.HTTP_201_CREATED
        )


class InscriptionPersonnelView(APIView):
    """
    POST /api/v1/auth/inscription/personnel/
    Inscription d'un opérateur de tri ou d'un responsable méthanisation (Control Center).
    Contrat 1.1.0 — Renvoie statut 201 avec les Jetons (access, refresh, utilisateur).
    """
    permission_classes = [EstAdmin]

    def post(self, request):
        from apps.comptes.serializers import InscriptionPersonnelSerializer
        serializer = InscriptionPersonnelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        utilisateur = serializer.save()

        # Émettre les jetons JWT immédiatement
        refresh = RefreshToken.for_user(utilisateur)
        refresh['role'] = utilisateur.role
        refresh['nom'] = utilisateur.nom

        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "utilisateur": UtilisateurSerializer(utilisateur).data
        }, status=status.HTTP_201_CREATED)


class OtpVerifierView(APIView):
    """
    POST /api/v1/auth/otp/verifier/
    Validation du code OTP reçu par SMS.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = OtpVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        otp = serializer.validated_data['otp']
        otp.utilise = True
        otp.save()

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
