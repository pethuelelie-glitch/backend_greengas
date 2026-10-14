import json
from decimal import Decimal
from django.db import transaction

from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.collecte.models import (
    Collecte, StatutCollecte, StatutControle, SourceMesure, Scan
)
from apps.collecte.serializers import (
    CollecteSerializer,
    PeseeRequeteSerializer,
)
from apps.collecte.utils import get_parametre
from apps.comptes.exceptions import MetierException
from apps.comptes.models import Role, Utilisateur
from apps.comptes.permissions import EstAdminOuReferent
from apps.supervision.models import JournalAudit, TypeObjet


class CollecteListView(generics.ListAPIView):
    """
    GET /api/v1/collectes/ — Liste des collectes.
    Filtres : tournee_id, bac_id, statut, statut_controle. Inclut code_bac.
    """
    serializer_class = CollecteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == Role.ADMINISTRATEUR or user.is_superuser:
            queryset = Collecte.objects.all()
        elif user.role == Role.COLLECTEUR:
            queryset = Collecte.objects.filter(collecteur=user)
        elif user.role == Role.REFERENT and user.bac_id:
            queryset = Collecte.objects.filter(bac_id=user.bac_id)
        else:
            queryset = Collecte.objects.none()

        tournee_id = self.request.query_params.get('tournee_id') or self.request.query_params.get('tournee')
        if tournee_id:
            queryset = queryset.filter(tournee_id=tournee_id)

        bac_id = self.request.query_params.get('bac_id') or self.request.query_params.get('bac')
        if bac_id:
            queryset = queryset.filter(bac_id=bac_id)

        statut = self.request.query_params.get('statut')
        if statut:
            queryset = queryset.filter(statut=statut)

        statut_controle = self.request.query_params.get('statut_controle')
        if statut_controle:
            queryset = queryset.filter(statut_controle=statut_controle)

        return queryset.order_by('-date_ouverture')


class CollecteDetailView(generics.RetrieveAPIView):
    """
    GET /api/v1/collectes/{id}/ — Détail d'une collecte.
    """
    serializer_class = CollecteSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'

    def get_queryset(self):
        user = self.request.user
        if user.role == Role.ADMINISTRATEUR or user.is_superuser:
            return Collecte.objects.all()
        if user.role == Role.COLLECTEUR:
            return Collecte.objects.filter(collecteur=user)
        if user.role == Role.REFERENT and user.bac_id:
            return Collecte.objects.filter(bac_id=user.bac_id)
        return Collecte.objects.none()


class CollectePeseeView(APIView):
    """
    POST /api/v1/collectes/{id}/pesee/
    Capteur / simulateur : enregistre la pesée brute et calcule le poids net.
    Passage de 'en_attente_pesee' à 'pesee'.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, id=None, pk=None):
        collecte_id = id or pk
        collecte = generics.get_object_or_404(
            Collecte.objects.select_for_update(), id=collecte_id
        )
        if request.user.role not in [Role.ADMINISTRATEUR, Role.CAPTEUR] and not request.user.is_superuser:
            raise PermissionDenied("Seuls un administrateur ou un capteur peuvent enregistrer une pesée")

        if collecte.statut != StatutCollecte.EN_ATTENTE_PESEE:
            raise MetierException(
                code="STATUT_INVALIDE",
                message=f"La pesée ne peut être enregistrée que sur une collecte 'en_attente_pesee' (statut actuel: '{collecte.statut}')"
            )

        serializer = PeseeRequeteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        poids_brut = Decimal(str(serializer.validated_data['poids_brut_kg']))
        source = serializer.validated_data.get('source', SourceMesure.CAPTEUR)
        tare = Decimal(str(collecte.tare_kg))
        poids_net = max(Decimal('0.00'), round(poids_brut - tare, 2))

        collecte.poids_brut_kg = poids_brut
        collecte.poids_net_kg = poids_net
        collecte.source = source
        collecte.statut = StatutCollecte.PESEE
        collecte.date_pesee = timezone.now()
        collecte.save()

        return Response(CollecteSerializer(collecte).data, status=status.HTTP_200_OK)


class CollecteValiderView(APIView):
    """
    POST /api/v1/collectes/{id}/valider/
    Le collecteur valide la pesée.
    Calcule scans_valides, kg_par_scan et statut_controle (a_verifier si kg_par_scan < 0.3).
    Met à jour bac.date_derniere_collecte.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, id=None, pk=None):
        collecte_id = id or pk
        collecte = generics.get_object_or_404(
            Collecte.objects.select_for_update(), id=collecte_id
        )

        if not (request.user.is_superuser or request.user.role == Role.ADMINISTRATEUR or
                (request.user.role == Role.COLLECTEUR and collecte.collecteur_id == request.user.id)):
            raise PermissionDenied("Vous n'êtes pas le collecteur assigné à cette collecte")

        if collecte.statut != StatutCollecte.PESEE:
            raise MetierException(
                code="STATUT_INVALIDE",
                message=f"La collecte ne peut être validée que si elle est au statut 'pesee' (statut actuel: '{collecte.statut}')"
            )

        # 1. Calcul des scans valides sur la période
        scans_qs = Scan.objects.filter(bac=collecte.bac, compte=True)
        if collecte.bac.date_derniere_collecte:
            scans_qs = scans_qs.filter(horodatage__gt=collecte.bac.date_derniere_collecte)
        scans_valides = scans_qs.count()

        # 2. Calcul du ratio kg par scan
        poids_net = collecte.poids_net_kg if collecte.poids_net_kg is not None else Decimal('0.00')
        if scans_valides > 0:
            kg_par_scan = round(Decimal(str(poids_net)) / Decimal(scans_valides), 3)
        else:
            kg_par_scan = Decimal('0.000')

        # 3. Contrôle antifraude : a_verifier si kg_par_scan < seuil (défaut 0.3)
        seuil_kg = Decimal(str(get_parametre('seuil_kg_par_scan', 0.3)))
        if kg_par_scan < seuil_kg:
            statut_controle = StatutControle.A_VERIFIER
        else:
            statut_controle = StatutControle.NORMAL

        now = timezone.now()
        collecte.scans_valides = scans_valides
        collecte.kg_par_scan = kg_par_scan
        collecte.statut_controle = statut_controle
        collecte.statut = StatutCollecte.VALIDEE
        collecte.date_validation = now
        collecte.save()

        # 4. Mise à jour de la date de dernière collecte du bac
        collecte.bac.date_derniere_collecte = now
        collecte.bac.save(update_fields=['date_derniere_collecte'])

        # Notification collecte_a_verifier si statut de contrôle a_verifier (Contrat 1.4.0)
        if statut_controle == StatutControle.A_VERIFIER:
            try:
                from apps.supervision.models import TypeNotification, NiveauNotification
                from apps.supervision.services import notifier_utilisateurs
                admins = list(Utilisateur.objects.filter(role=Role.ADMINISTRATEUR, actif=True))
                referents = list(Utilisateur.objects.filter(bac=collecte.bac, role=Role.REFERENT, actif=True))
                dest = list({u.id: u for u in (admins + referents)}.values())
                notifier_utilisateurs(
                    destinataires=dest,
                    type=TypeNotification.COLLECTE_A_VERIFIER,
                    niveau=NiveauNotification.ATTENTION,
                    titre="Collecte à vérifier",
                    message=f"{collecte.bac.code} : {poids_net:.0f} kg pour {scans_valides} scans ({kg_par_scan:.2f} kg/scan).",
                    objet_type="collecte",
                    objet_id=collecte.id,
                    auteur=request.user
                )
            except Exception:
                pass

        return Response(CollecteSerializer(collecte).data, status=status.HTTP_200_OK)


class CollecteDecisionView(APIView):
    """
    POST /api/v1/collectes/{id}/decision/
    L'administrateur ou référent tranche sur une collecte 'a_verifier'.
    Décision : 'valider_points' ou 'annuler_points'.
    Action tracée dans le JournalAudit.
    """
    permission_classes = [EstAdminOuReferent]

    @transaction.atomic
    def post(self, request, id=None, pk=None):
        collecte_id = id or pk
        collecte = generics.get_object_or_404(
            Collecte.objects.select_for_update(), id=collecte_id
        )

        if request.user.role == Role.REFERENT and collecte.bac_id != request.user.bac_id:
            raise PermissionDenied("Cette collecte ne concerne pas votre bac")

        if collecte.statut_controle != StatutControle.A_VERIFIER:
            raise MetierException(
                code="STATUT_INVALIDE",
                message=f"Seules les collectes avec le statut de contrôle 'a_verifier' peuvent faire l'objet d'une décision (statut actuel: '{collecte.statut_controle}')"
            )

        decision = request.data.get('decision')
        motif = request.data.get('motif', '')

        if decision == 'valider_points':
            nouvel_etat = StatutControle.POINTS_VALIDES
        elif decision == 'annuler_points':
            nouvel_etat = StatutControle.POINTS_ANNULES
        else:
            raise MetierException(
                code="DECISION_INVALIDE",
                message="La décision doit être 'valider_points' ou 'annuler_points'"
            )

        ancien_etat = collecte.statut_controle
        collecte.statut_controle = nouvel_etat
        collecte.save(update_fields=['statut_controle'])

        # Enregistrement dans le journal d'audit immuable
        JournalAudit.objects.create(
            auteur=request.user,
            action=f"collecte.{decision}",
            objet_type=TypeObjet.COLLECTE,
            objet_id=str(collecte.id),
            ancienne_valeur=json.dumps({"statut_controle": ancien_etat}),
            nouvelle_valeur=json.dumps({"statut_controle": nouvel_etat}),
            motif=motif or f"Décision administrative : {decision}"
        )

        # Synchronisation des transactions GreenPoints rattachées et notifications citoyen (Contrat 1.4.0)
        try:
            from apps.greenpoints.models import GreenPointsTransaction, StatutTransaction
            from apps.supervision.models import TypeNotification, NiveauNotification
            from apps.supervision.services import creer_notification
            date_str = collecte.tournee.date.strftime('%d/%m') if collecte.tournee else "récente"

            if decision == 'valider_points':
                tx_qs = collecte.transactions_points.filter(statut=StatutTransaction.EN_ATTENTE)
                for tx in tx_qs:
                    tx.statut = StatutTransaction.CREDITEE
                    tx.save(update_fields=['statut'])
                    creer_notification(
                        destinataire=tx.citoyen,
                        type=TypeNotification.POINTS_CREDITES,
                        niveau=NiveauNotification.INFO,
                        titre="Points crédités",
                        message=f"+{tx.points} points pour la collecte du {date_str} ({collecte.bac.code}).",
                        objet_type="transaction",
                        objet_id=tx.id,
                        auteur=request.user
                    )
            elif decision == 'annuler_points':
                tx_qs = collecte.transactions_points.exclude(statut=StatutTransaction.ANNULEE)
                for tx in tx_qs:
                    tx.statut = StatutTransaction.ANNULEE
                    tx.save(update_fields=['statut'])
                    creer_notification(
                        destinataire=tx.citoyen,
                        type=TypeNotification.POINTS_ANNULES,
                        niveau=NiveauNotification.ATTENTION,
                        titre="Points annulés",
                        message=f"{tx.points} points annulés après vérification ({collecte.bac.code}).",
                        objet_type="transaction",
                        objet_id=tx.id,
                        auteur=request.user
                    )
        except Exception:
            pass

        return Response(CollecteSerializer(collecte).data, status=status.HTTP_200_OK)
