import json
from django.db import transaction
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from apps.comptes.models import Utilisateur, Role, StatutValidation
from apps.comptes.serializers import UtilisateurSerializer
from apps.comptes.permissions import EstAdmin
from apps.comptes.exceptions import (
    ConflitException,
    EmailDejaUtiliseException,
    TelephoneDejaUtiliseException,
)


class UtilisateurListCreateView(generics.ListCreateAPIView):
    """
    GET /api/v1/utilisateurs/ — Liste des utilisateurs (administrateur ; référent = citoyens de sa résidence)
    POST /api/v1/utilisateurs/ — Création d'un utilisateur par l'admin
    """
    serializer_class = UtilisateurSerializer
    permission_classes = [EstAdmin]

    def get_queryset(self):
        user = self.request.user
        queryset = Utilisateur.objects.all().order_by('-date_creation')

        # Référent : uniquement citoyens de sa résidence/bac
        if user.role == Role.REFERENT and not user.is_superuser:
            if user.bac:
                queryset = queryset.filter(bac=user.bac, role=Role.CITOYEN)
            else:
                queryset = queryset.none()

        role = self.request.query_params.get('role')
        if role:
            queryset = queryset.filter(role=role)
        statut = self.request.query_params.get('statut_validation')
        if statut:
            queryset = queryset.filter(statut_validation=statut)
        bac_id = self.request.query_params.get('bac_id')
        if bac_id:
            queryset = queryset.filter(bac_id=bac_id)
        recherche = self.request.query_params.get('recherche')
        if recherche:
            queryset = queryset.filter(nom__icontains=recherche)
        return queryset

    def perform_create(self, serializer):
        email = self.request.data.get('email')
        if email:
            email_clean = email.strip().lower()
            if Utilisateur.objects.filter(email__iexact=email_clean).exists():
                raise EmailDejaUtiliseException(
                    details={"email": ["Cette adresse e-mail est déjà utilisée."]}
                )
        telephone = self.request.data.get('telephone')
        if telephone:
            tel_clean = telephone.strip()
            if Utilisateur.objects.filter(telephone=tel_clean).exists():
                raise TelephoneDejaUtiliseException(
                    details={"telephone": ["Ce numéro de téléphone est déjà utilisé."]}
                )
        serializer.save()


class UtilisateurDetailView(generics.RetrieveUpdateAPIView):
    """
    GET /api/v1/utilisateurs/{id}/
    PATCH /api/v1/utilisateurs/{id}/
    """
    queryset = Utilisateur.objects.all()
    serializer_class = UtilisateurSerializer
    permission_classes = [EstAdmin]
    lookup_field = 'id'

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        new_email = request.data.get('email')
        if new_email:
            email_clean = new_email.strip().lower()
            if Utilisateur.objects.filter(email__iexact=email_clean).exclude(id=instance.id).exists():
                raise EmailDejaUtiliseException(
                    details={"email": ["Cette adresse e-mail est déjà utilisée."]}
                )
        new_tel = request.data.get('telephone')
        if new_tel:
            tel_clean = new_tel.strip()
            if Utilisateur.objects.filter(telephone=tel_clean).exclude(id=instance.id).exists():
                raise TelephoneDejaUtiliseException(
                    details={"telephone": ["Ce numéro de téléphone est déjà utilisé."]}
                )
        return super().update(request, *args, **kwargs)


class UtilisateurValidationView(APIView):
    """
    POST /api/v1/utilisateurs/{id}/validation/ — OpenAPI 1.3.0
    Valider ou refuser un compte du personnel en attente (administrateur seulement) — journalisé.
    Depuis 1.3.0, seuls les comptes operateur_tri et responsable_methanisation inscrits eux-mêmes
    passent par cette validation. Un compte qui n'est pas en_attente renvoie 409 CONFLIT ;
    un autre rôle que administrateur reçoit 403 ACCES_REFUSE. Refuser laisse le compte refusé (connexion impossible).
    """
    permission_classes = [EstAdmin]

    @transaction.atomic
    def post(self, request, id):
        utilisateur = generics.get_object_or_404(
            Utilisateur.objects.select_for_update(), id=id
        )

        # Ne concerne que les comptes du personnel en attente -> sinon 409 CONFLIT ("Ce compte n'attend pas de validation.")
        if utilisateur.role not in [Role.OPERATEUR_TRI, Role.RESPONSABLE_METHANISATION] or utilisateur.statut_validation != StatutValidation.EN_ATTENTE:
            raise ConflitException(
                code="CONFLIT",
                message="Ce compte n'attend pas de validation.",
                details={"statut_validation": utilisateur.statut_validation}
            )

        decision = request.data.get('decision')
        commentaire = request.data.get('commentaire')

        if decision == 'valider':
            utilisateur.statut_validation = StatutValidation.VALIDE
        elif decision == 'refuser':
            utilisateur.statut_validation = StatutValidation.REFUSE
        else:
            return Response(
                {
                    "code": "VALIDATION",
                    "message": "Le champ 'decision' est requis et doit valoir 'valider' ou 'refuser'.",
                    "details": {"decision": ["Valeur invalide."]}
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        utilisateur.save()

        from apps.supervision.models import JournalAudit, TypeObjet
        JournalAudit.objects.create(
            auteur=request.user,
            action=f"utilisateur.{decision}",
            objet_type=TypeObjet.UTILISATEUR,
            objet_id=str(utilisateur.id),
            ancienne_valeur=json.dumps({"statut_validation": "en_attente"}),
            nouvelle_valeur=json.dumps({"statut_validation": utilisateur.statut_validation}),
            motif=commentaire or f"Validation personnel : {decision}"
        )

        return Response(UtilisateurSerializer(utilisateur).data, status=status.HTTP_200_OK)
