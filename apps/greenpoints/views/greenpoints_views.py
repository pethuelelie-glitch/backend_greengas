import json
from django.db import transaction
from django.db.models import Sum
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.comptes.exceptions import MetierException
from apps.comptes.models import Role, Utilisateur
from apps.comptes.permissions import EstAdmin, EstCitoyen
from apps.greenpoints.models import (
    GreenPointsTransaction, StatutTransaction,
    Recompense, Echange
)
from apps.greenpoints.serializers import (
    GreenPointsTransactionSerializer,
    SoldeSerializer,
    RecompenseSerializer,
    RecompenseEcritureSerializer,
    EchangeSerializer,
    EchangeCreationSerializer,
)
from apps.supervision.models import JournalAudit, TypeObjet


class GreenPointsSoldeView(APIView):
    """
    GET /api/v1/greenpoints/solde/
    Solde de GreenPoints du citoyen connecté (ou d'un citoyen donné pour l'administrateur).
    Calcul :
      total_gagne = somme des transactions créditées
      total_echange = somme des coûts en points des échanges effectués
      solde = total_gagne - total_echange
      points_en_attente = somme des transactions en attente
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        citoyen_id = request.query_params.get('citoyen_id')

        if user.role not in [Role.CITOYEN, Role.ADMINISTRATEUR] and not user.is_superuser:
            raise PermissionDenied("Cette ressource est réservée aux citoyens et aux administrateurs")

        if citoyen_id and (user.role == Role.ADMINISTRATEUR or user.is_superuser):
            citoyen = generics.get_object_or_404(Utilisateur, id=citoyen_id)
            if citoyen.role != Role.CITOYEN:
                raise PermissionDenied("Le solde ne peut être consulté que pour un citoyen")
        else:
            citoyen = user

        total_gagne = GreenPointsTransaction.objects.filter(
            citoyen=citoyen,
            statut=StatutTransaction.CREDITEE
        ).aggregate(total=Sum('points'))['total'] or 0

        points_en_attente = GreenPointsTransaction.objects.filter(
            citoyen=citoyen,
            statut=StatutTransaction.EN_ATTENTE
        ).aggregate(total=Sum('points'))['total'] or 0

        total_echange = Echange.objects.filter(
            citoyen=citoyen
        ).aggregate(total=Sum('cout_points'))['total'] or 0

        solde = total_gagne - total_echange

        data = {
            "citoyen_id": citoyen.id,
            "solde": solde,
            "points_en_attente": points_en_attente,
            "total_gagne": total_gagne,
            "total_echange": total_echange,
        }

        return Response(SoldeSerializer(data).data, status=status.HTTP_200_OK)


class GreenPointsTransactionListView(generics.ListAPIView):
    """
    GET /api/v1/greenpoints/transactions/
    Historique des gains de GreenPoints. Un citoyen ne voit que les siens.
    Filtres : citoyen_id, tournee_id, statut. Inclut code_tournee.
    """
    serializer_class = GreenPointsTransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == Role.CITOYEN:
            queryset = GreenPointsTransaction.objects.filter(citoyen=user)
        elif user.role == Role.ADMINISTRATEUR or user.is_superuser:
            queryset = GreenPointsTransaction.objects.all()
            citoyen_id = self.request.query_params.get('citoyen_id')
            if citoyen_id:
                queryset = queryset.filter(citoyen_id=citoyen_id)
        else:
            queryset = GreenPointsTransaction.objects.none()

        tournee_id = self.request.query_params.get('tournee_id')
        if tournee_id:
            queryset = queryset.filter(tournee_id=tournee_id)

        statut = self.request.query_params.get('statut')
        if statut:
            queryset = queryset.filter(statut=statut)

        return queryset.select_related('citoyen', 'bac', 'tournee', 'collecte').order_by('-date')


class RecompenseListCreateView(generics.ListCreateAPIView):
    """
    GET /api/v1/recompenses/ — Catalogue des récompenses (non paginé). Filtre : actif.
    POST /api/v1/recompenses/ — Ajouter une récompense (administrateur).
    """
    pagination_class = None

    def get_permissions(self):
        if self.request.method == 'POST':
            return [EstAdmin()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return RecompenseEcritureSerializer
        return RecompenseSerializer

    def get_queryset(self):
        queryset = Recompense.objects.all().order_by('cout_points')
        if self.request.user.role != Role.ADMINISTRATEUR and not self.request.user.is_superuser:
            queryset = queryset.filter(actif=True)
        actif = self.request.query_params.get('actif')
        if actif is not None:
            if actif.lower() in ['true', '1', 't']:
                queryset = queryset.filter(actif=True)
            elif actif.lower() in ['false', '0', 'f']:
                queryset = queryset.filter(actif=False)
        return queryset

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        recompense = serializer.save()

        # Enregistrement dans le journal d'audit
        JournalAudit.objects.create(
            auteur=request.user,
            action="recompense.creer",
            objet_type=TypeObjet.RECOMPENSE,
            objet_id=str(recompense.id),
            nouvelle_valeur=json.dumps({
                "nom": recompense.nom,
                "cout_points": recompense.cout_points,
                "partenaire": recompense.partenaire,
                "actif": recompense.actif,
            }),
            motif=f"Création de la récompense '{recompense.nom}'"
        )

        return Response(RecompenseSerializer(recompense).data, status=status.HTTP_201_CREATED)


class RecompenseDetailView(generics.RetrieveUpdateAPIView):
    """
    GET /api/v1/recompenses/{id}/ — Détail d'une récompense
    PATCH /api/v1/recompenses/{id}/ — Modifier une récompense (administrateur)
    """
    serializer_class = RecompenseEcritureSerializer
    lookup_field = 'id'

    def get_queryset(self):
        queryset = Recompense.objects.all()
        if self.request.user.role != Role.ADMINISTRATEUR and not self.request.user.is_superuser:
            queryset = queryset.filter(actif=True)
        return queryset

    def get_permissions(self):
        if self.request.method in ['PATCH', 'PUT']:
            return [EstAdmin()]
        return [IsAuthenticated()]

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', True)
        instance = self.get_object()
        instance = Recompense.objects.select_for_update().get(pk=instance.pk)
        ancien_etat = {
            "nom": instance.nom,
            "cout_points": instance.cout_points,
            "partenaire": instance.partenaire,
            "actif": instance.actif,
        }

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        instance.refresh_from_db()
        nouveau_etat = {
            "nom": instance.nom,
            "cout_points": instance.cout_points,
            "partenaire": instance.partenaire,
            "actif": instance.actif,
        }

        # Enregistrement dans le journal d'audit
        JournalAudit.objects.create(
            auteur=request.user,
            action="recompense.modifier",
            objet_type=TypeObjet.RECOMPENSE,
            objet_id=str(instance.id),
            ancienne_valeur=json.dumps(ancien_etat),
            nouvelle_valeur=json.dumps(nouveau_etat),
            motif=f"Modification de la récompense '{instance.nom}'"
        )

        return Response(RecompenseSerializer(instance).data, status=status.HTTP_200_OK)


class EchangeListCreateView(generics.ListCreateAPIView):
    """
    GET /api/v1/echanges/ — Historique des échanges (un citoyen ne voit que les siens). Filtre : citoyen_id.
    POST /api/v1/echanges/ — Échanger des points contre une récompense (citoyen).
    """
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == 'POST':
            return [EstCitoyen()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return EchangeCreationSerializer
        return EchangeSerializer

    def get_queryset(self):
        user = self.request.user
        if user.role == Role.CITOYEN:
            queryset = Echange.objects.filter(citoyen=user)
        elif user.role == Role.ADMINISTRATEUR or user.is_superuser:
            queryset = Echange.objects.all()
            citoyen_id = self.request.query_params.get('citoyen_id')
            if citoyen_id:
                queryset = queryset.filter(citoyen_id=citoyen_id)
        else:
            queryset = Echange.objects.none()

        return queryset.select_related('citoyen', 'recompense').order_by('-date')

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        if request.user.role != Role.CITOYEN:
            raise PermissionDenied("Seuls les citoyens peuvent échanger leurs GreenPoints")
        citoyen = Utilisateur.objects.select_for_update().get(pk=request.user.pk)
        serializer = EchangeCreationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        recompense_id = serializer.validated_data['recompense_id']

        recompense = generics.get_object_or_404(Recompense, id=recompense_id)

        # 1. Vérification : récompense active
        if not recompense.actif:
            raise MetierException(
                code="RECOMPENSE_INACTIVE",
                message="Cette récompense n'est plus disponible au catalogue"
            )

        # 2. Calcul du solde disponible du citoyen
        total_gagne = GreenPointsTransaction.objects.filter(
            citoyen=citoyen,
            statut=StatutTransaction.CREDITEE
        ).aggregate(total=Sum('points'))['total'] or 0

        total_echange = Echange.objects.filter(
            citoyen=citoyen
        ).aggregate(total=Sum('cout_points'))['total'] or 0

        solde_disponible = total_gagne - total_echange

        # 3. Vérification : solde suffisant
        if solde_disponible < recompense.cout_points:
            raise MetierException(
                code="SOLDE_INSUFFISANT",
                message=f"Solde insuffisant : vous disposez de {solde_disponible} points, mais {recompense.cout_points} points sont requis",
                details={"solde": solde_disponible, "cout_points": recompense.cout_points}
            )

        # 4. Création atomique de l'échange
        with transaction.atomic():
            echange = Echange.objects.create(
                citoyen=citoyen,
                recompense=recompense,
                cout_points=recompense.cout_points
            )

            JournalAudit.objects.create(
                auteur=citoyen,
                action="echange.creer",
                objet_type=TypeObjet.ECHANGE,
                objet_id=str(echange.id),
                nouvelle_valeur=json.dumps({
                    "recompense": recompense.nom,
                    "cout_points": recompense.cout_points,
                    "solde_apres": solde_disponible - recompense.cout_points
                }),
                motif=f"Échange de {recompense.cout_points} GreenPoints contre {recompense.nom}"
            )

            # Notification echange_effectue au citoyen (Contrat 1.4.0)
            try:
                from apps.supervision.models import TypeNotification, NiveauNotification
                from apps.supervision.services import creer_notification
                creer_notification(
                    destinataire=citoyen,
                    type=TypeNotification.ECHANGE_EFFECTUE,
                    niveau=NiveauNotification.INFO,
                    titre="Récompense échangée",
                    message=f"{recompense.nom} échangé contre {recompense.cout_points} points.",
                    objet_type=None,
                    objet_id=None
                )
            except Exception:
                pass

        return Response(EchangeSerializer(echange).data, status=status.HTTP_201_CREATED)
