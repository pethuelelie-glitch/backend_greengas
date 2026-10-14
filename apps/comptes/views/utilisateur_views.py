from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from apps.comptes.models import Utilisateur, Role, StatutValidation
from apps.comptes.serializers import UtilisateurSerializer
from apps.comptes.permissions import EstAdmin, EstAdminOuReferent


class UtilisateurListCreateView(generics.ListCreateAPIView):
    """
    GET /api/v1/utilisateurs/ — Liste des utilisateurs (filtrable par rôle)
    POST /api/v1/utilisateurs/ — Création d'un utilisateur par l'admin
    """
    serializer_class = UtilisateurSerializer
    permission_classes = [EstAdmin]

    def get_queryset(self):
        queryset = Utilisateur.objects.all().order_by('-date_creation')
        role = self.request.query_params.get('role')
        if role:
            queryset = queryset.filter(role=role)
        statut = self.request.query_params.get('statut_validation')
        if statut:
            queryset = queryset.filter(statut_validation=statut)
        return queryset


class UtilisateurDetailView(generics.RetrieveUpdateAPIView):
    """
    GET /api/v1/utilisateurs/{id}/
    PATCH /api/v1/utilisateurs/{id}/
    """
    queryset = Utilisateur.objects.all()
    serializer_class = UtilisateurSerializer
    permission_classes = [EstAdmin]
    lookup_field = 'id'


class UtilisateurValidationView(APIView):
    """
    POST /api/v1/utilisateurs/{id}/validation/
    Validation ou refus d'un compte citoyen par le référent ou l'administrateur.
    Payload: { "decision": "valider" | "refuser" }
    """
    permission_classes = [EstAdminOuReferent]

    def post(self, request, id):
        utilisateur = generics.get_object_or_404(Utilisateur, id=id)

        if utilisateur.role != Role.CITOYEN:
            return Response(
                {"code": "VALIDATION", "message": "Seuls les citoyens peuvent être validés", "details": {}},
                status=status.HTTP_400_BAD_REQUEST
            )

        decision = request.data.get('decision')
        if decision == 'valider':
            utilisateur.statut_validation = StatutValidation.VALIDE
        elif decision == 'refuser':
            utilisateur.statut_validation = StatutValidation.REFUSE
        else:
            return Response(
                {"code": "VALIDATION", "message": "La décision doit être 'valider' ou 'refuser'", "details": {}},
                status=status.HTTP_400_BAD_REQUEST
            )

        utilisateur.save()
        return Response(UtilisateurSerializer(utilisateur).data, status=status.HTTP_200_OK)
