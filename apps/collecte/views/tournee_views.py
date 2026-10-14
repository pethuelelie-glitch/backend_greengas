from django.utils import timezone
from django.db import transaction
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.collecte.models import (
    Tournee, StatutTournee, MotifAffectation,
    Collecte, StatutCollecte
)
from apps.collecte.serializers import (
    TourneeSerializer,
    TourneeDetailSerializer,
    TourneeCreationSerializer,
    CollecteSerializer,
)
from apps.comptes.exceptions import MetierException, ConflitException
from apps.comptes.models import Role, Utilisateur
from apps.comptes.permissions import EstAdmin
from apps.referentiel.models import Bac, StatutBac, StatutSite


class TourneeListCreateView(generics.ListCreateAPIView):
    """
    GET /api/v1/tournees/ — Liste des tournées (le collecteur ne voit que les siennes).
    POST /api/v1/tournees/ — Création d'une tournée par l'administrateur.
    """
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return TourneeCreationSerializer
        return TourneeSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [EstAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if user.role == Role.ADMINISTRATEUR or user.is_superuser:
            queryset = Tournee.objects.all()
        elif user.role == Role.COLLECTEUR:
            queryset = Tournee.objects.filter(collecteur=user)
        elif user.role == Role.REFERENT and user.bac_id:
            queryset = Tournee.objects.filter(secteur_id=user.bac.secteur_id)
        else:
            queryset = Tournee.objects.none()

        date_val = self.request.query_params.get('date')
        if date_val:
            queryset = queryset.filter(date=date_val)

        statut = self.request.query_params.get('statut')
        if statut:
            queryset = queryset.filter(statut=statut)

        secteur_id = self.request.query_params.get('secteur_id') or self.request.query_params.get('secteur')
        if secteur_id:
            queryset = queryset.filter(secteur_id=secteur_id)

        collecteur_id = self.request.query_params.get('collecteur_id') or self.request.query_params.get('collecteur')
        if collecteur_id:
            queryset = queryset.filter(collecteur_id=collecteur_id)

        return queryset.order_by('-date', 'code')

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = TourneeCreationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        secteur = serializer.validated_data['secteur']
        date_val = serializer.validated_data['date']
        collecteur = serializer.validated_data['collecteur']
        bacs = serializer.validated_data.get('bacs')

        # Calcul automatique du site de destination
        if secteur.site.statut == StatutSite.MAINTENANCE:
            site = secteur.site_repli
            motif_affectation = MotifAffectation.REPLI
        else:
            site = secteur.site
            motif_affectation = MotifAffectation.SECTEUR

        # Génération du code TRN-MMDD-NN
        mmdd = date_val.strftime('%m%d')
        prefix = f"TRN-{mmdd}-"
        existing_codes = Tournee.objects.filter(code__startswith=prefix).values_list('code', flat=True)
        max_num = 0
        for c in existing_codes:
            try:
                num = int(c.split('-')[-1])
                if num > max_num:
                    max_num = num
            except (ValueError, IndexError):
                pass
        code = f"{prefix}{max_num + 1:02d}"

        # Bacs de la tournée
        if not bacs:
            bacs = list(Bac.objects.filter(secteur=secteur, statut=StatutBac.ACTIF))

        tournee = Tournee.objects.create(
            code=code,
            date=date_val,
            secteur=secteur,
            site=site,
            motif_affectation=motif_affectation,
            collecteur=collecteur,
            statut=StatutTournee.PLANIFIEE
        )
        tournee.bacs.set(bacs)

        # Création des entrées de collecte pour chaque bac
        for b in bacs:
            Collecte.objects.create(
                tournee=tournee,
                bac=b,
                collecteur=collecteur,
                tare_kg=b.tare_kg,
                statut=StatutCollecte.EN_ATTENTE_PESEE
            )

        # Notification tournee_planifiee au collecteur assigné (Contrat 1.4.0)
        try:
            from apps.supervision.models import TypeNotification, NiveauNotification
            from apps.supervision.services import creer_notification
            nb_bacs = len(bacs)
            creer_notification(
                destinataire=collecteur,
                type=TypeNotification.TOURNEE_PLANIFIEE,
                niveau=NiveauNotification.INFO,
                titre="Tournée planifiée",
                message=f"Nouvelle tournée {tournee.code} le {date_val.strftime('%d/%m')} ({secteur.code}, {nb_bacs} bacs).",
                objet_type="tournee",
                objet_id=tournee.id,
                auteur=request.user
            )
        except Exception:
            pass

        return Response(TourneeDetailSerializer(tournee).data, status=status.HTTP_201_CREATED)


class TourneeDetailView(generics.RetrieveAPIView):
    """
    GET /api/v1/tournees/{id}/ — Détail d'une tournée avec ses bacs et collectes.
    """
    serializer_class = TourneeDetailSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'

    def get_queryset(self):
        user = self.request.user
        if user.role == Role.ADMINISTRATEUR or user.is_superuser:
            return Tournee.objects.all()
        if user.role == Role.COLLECTEUR:
            return Tournee.objects.filter(collecteur=user)
        if user.role == Role.REFERENT and user.bac_id:
            return Tournee.objects.filter(secteur_id=user.bac.secteur_id)
        return Tournee.objects.none()

    def get_object(self):
        obj = super().get_object()
        user = self.request.user
        if user.role == Role.COLLECTEUR and obj.collecteur != user:
            raise PermissionDenied("Vous ne pouvez consulter que vos propres tournées")
        return obj


class TourneeDemarrerView(APIView):
    """
    POST /api/v1/tournees/{id}/demarrer/
    Passage de la tournée de 'planifiee' à 'en_cours'.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, id=None, pk=None):
        tournee_id = id or pk
        tournee = generics.get_object_or_404(
            Tournee.objects.select_for_update(), id=tournee_id
        )

        if not (request.user.is_superuser or request.user.role == Role.ADMINISTRATEUR or
                (request.user.role == Role.COLLECTEUR and tournee.collecteur_id == request.user.id)):
            raise PermissionDenied("Vous n'êtes pas le collecteur assigné à cette tournée")

        if tournee.statut != StatutTournee.PLANIFIEE:
            raise MetierException(
                code="STATUT_INVALIDE",
                message=f"La tournée ne peut pas être démarrée car son statut actuel est '{tournee.statut}' (attendu: 'planifiee')"
            )

        tournee.statut = StatutTournee.EN_COURS
        tournee.save(update_fields=['statut'])
        return Response(TourneeDetailSerializer(tournee).data, status=status.HTTP_200_OK)


class TourneeCollecteOuvrirView(APIView):
    """
    POST /api/v1/tournees/{id}/collectes/
    Le collecteur ouvre une collecte pour un bac via son code.
    Valide que le bac est dans la tournée et non déjà collecté.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, id=None, pk=None):
        tournee_id = id or pk
        tournee = generics.get_object_or_404(
            Tournee.objects.select_for_update(), id=tournee_id
        )

        if not (request.user.is_superuser or request.user.role == Role.ADMINISTRATEUR or
                (request.user.role == Role.COLLECTEUR and tournee.collecteur_id == request.user.id)):
            raise PermissionDenied("Vous n'êtes pas le collecteur assigné à cette tournée")

        if tournee.statut != StatutTournee.EN_COURS:
            raise MetierException(
                code="TOURNEE_NON_DEMARREE",
                message="La tournée doit être 'en_cours' pour ouvrir une collecte"
            )

        code_bac = request.data.get('code_bac') or request.data.get('code')
        bac_id = request.data.get('bac_id') or request.data.get('bac')

        bac = None
        if code_bac:
            bac = Bac.objects.filter(code=code_bac).first()
        elif bac_id:
            bac = Bac.objects.filter(id=bac_id).first()

        if not bac:
            raise MetierException(
                code="BAC_INTROUVABLE",
                message="Le bac spécifié est introuvable",
                status_code=status.HTTP_404_NOT_FOUND
            )

        # 1. Valider que le bac fait partie de la tournée
        if not tournee.bacs.filter(id=bac.id).exists():
            raise MetierException(
                code="BAC_HORS_TOURNEE",
                message="Ce bac n'est pas prévu dans cette tournée"
            )

        # 2. Valider que le bac n'est pas déjà collecté
        collecte = Collecte.objects.filter(tournee=tournee, bac=bac).first()
        if collecte:
            if collecte.statut in [StatutCollecte.PESEE, StatutCollecte.VALIDEE]:
                raise ConflitException(
                    code="DEJA_COLLECTE",
                    message="Ce bac a déjà été collecté lors de cette tournée"
                )
            collecte.date_ouverture = timezone.now()
            collecte.save(update_fields=['date_ouverture'])
            return Response(CollecteSerializer(collecte).data, status=status.HTTP_200_OK)
        else:
            collecteur_user = request.user if request.user.role == Role.COLLECTEUR else tournee.collecteur
            collecte = Collecte.objects.create(
                tournee=tournee,
                bac=bac,
                collecteur=collecteur_user,
                tare_kg=bac.tare_kg,
                statut=StatutCollecte.EN_ATTENTE_PESEE
            )
            return Response(CollecteSerializer(collecte).data, status=status.HTTP_201_CREATED)


class TourneeCloturerView(APIView):
    """
    POST /api/v1/tournees/{id}/cloturer/
    Clôture d'une tournée : passage de 'en_cours' à 'collectee'.
    Toutes les collectes de la tournée doivent être au statut 'validee'.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, id=None, pk=None):
        tournee_id = id or pk
        tournee = generics.get_object_or_404(
            Tournee.objects.select_for_update(), id=tournee_id
        )

        if not (request.user.is_superuser or request.user.role == Role.ADMINISTRATEUR or
                (request.user.role == Role.COLLECTEUR and tournee.collecteur_id == request.user.id)):
            raise PermissionDenied("Vous n'êtes pas le collecteur assigné à cette tournée")

        if tournee.statut != StatutTournee.EN_COURS:
            raise MetierException(
                code="STATUT_INVALIDE",
                message=f"La tournée ne peut pas être clôturée car son statut actuel est '{tournee.statut}' (attendu: 'en_cours')"
            )

        bacs_ids = set(tournee.bacs.values_list('id', flat=True))
        collectes = Collecte.objects.filter(tournee=tournee)
        collectes_bac_ids = set(collectes.values_list('bac_id', flat=True))

        bacs_manquants = bacs_ids - collectes_bac_ids
        if bacs_manquants:
            raise MetierException(
                code="COLLECTES_INCOMPLETES",
                message="Certains bacs prévus dans la tournée n'ont pas encore été collectés"
            )

        non_validees = collectes.exclude(statut=StatutCollecte.VALIDEE)
        if non_validees.exists():
            raise MetierException(
                code="COLLECTES_NON_VALIDEES",
                message="Toutes les collectes de la tournée doivent être validées avant la clôture",
                details={"collectes_non_validees": [str(c.bac.code) for c in non_validees]}
            )

        tournee.statut = StatutTournee.COLLECTEE
        tournee.save(update_fields=['statut'])

        # Notification tournee_a_trier à tous les opérateurs de tri (Contrat 1.4.0)
        try:
            from apps.supervision.models import TypeNotification, NiveauNotification
            from apps.supervision.services import notifier_utilisateurs
            poids_total = sum((c.poids_net_kg or 0) for c in collectes)
            operateurs = Utilisateur.objects.filter(role=Role.OPERATEUR_TRI, actif=True, statut_validation='valide')
            notifier_utilisateurs(
                destinataires=operateurs,
                type=TypeNotification.TOURNEE_A_TRIER,
                niveau=NiveauNotification.INFO,
                titre="Tournée à trier",
                message=f"{tournee.code} ({tournee.secteur.code}, {poids_total:.0f} kg) attend son tri.",
                objet_type="tournee",
                objet_id=tournee.id,
                auteur=request.user
            )
        except Exception:
            pass

        return Response(TourneeDetailSerializer(tournee).data, status=status.HTTP_200_OK)
