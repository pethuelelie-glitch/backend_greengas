import json
from decimal import Decimal
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied

from apps.supervision.models import Parametre, JournalAudit, TypeObjet
from apps.supervision.serializers import (
    ParametreSerializer,
    ParametreUpdateSerializer,
    EntreeJournalSerializer,
    ElementVerificationSerializer,
    TracabiliteBacSerializer,
)
from apps.collecte.models import Collecte, StatutControle, Scan, StatutScan
from apps.collecte.serializers import CollecteSerializer, TourneeSerializer
from apps.comptes.models import Utilisateur, Role, StatutValidation
from apps.referentiel.models import Bac
from apps.referentiel.serializers import BacSerializer
from apps.tri.models import LotTrie
from apps.tri.serializers import LotTrieSerializer
from apps.greenpoints.models import GreenPointsTransaction
from apps.greenpoints.serializers import GreenPointsTransactionSerializer
from apps.energie.models import ProductionEnergie
from apps.energie.serializers import ProductionEnergieSerializer
from apps.comptes.permissions import EstAdmin, EstAdminOuReferent
from apps.comptes.exceptions import MetierException



class VerificationQueueView(APIView):
    """
    GET /api/v1/verifications/
    File de vérification non-paginée (administrateur ; référent limité à sa résidence/bac).
    Types pris en compte :
    - collecte_a_verifier : kg/scan anormal (< 0.3)
    - compte_en_attente : citoyens inscrits en attente de validation
    - scan_hors_zone : scan effectué à plus de 100 m du bac
    - scan_non_localise : scan sans coordonnées GPS valides
    - bac_surinscrit : nombre de citoyens validés > nombre de foyers déclarés
    Trié du plus ancien au plus récent.
    Filtre optionnel par query param 'type'.
    """
    permission_classes = [EstAdminOuReferent]

    def get(self, request):
        type_filter = request.query_params.get('type')
        user = request.user
        is_referent = (user.role == Role.REFERENT and not user.is_superuser)
        ref_bac = user.bac if is_referent else None

        elements = []

        # 1. Collectes à vérifier (collecte_a_verifier)
        if not type_filter or type_filter == 'collecte_a_verifier':
            collectes_qs = Collecte.objects.filter(
                statut_controle=StatutControle.A_VERIFIER
            ).select_related('bac', 'tournee')
            if is_referent:
                collectes_qs = collectes_qs.filter(bac=ref_bac) if ref_bac else collectes_qs.none()

            for col in collectes_qs:
                poids_net = float(col.poids_net_kg or 0)
                scans = col.scans_valides or 0
                kg_scan = float(col.kg_par_scan or 0)
                d = col.date_validation or col.date_pesee or col.date_ouverture
                elements.append({
                    'type': 'collecte_a_verifier',
                    'objet_type': TypeObjet.COLLECTE,
                    'objet_id': str(col.id),
                    'libelle': f"{col.bac.code} : {poids_net:.2f} kg pour {scans} scans ({kg_scan:.2f} kg/scan)",
                    'details': {
                        'poids_net_kg': poids_net,
                        'scans_valides': scans,
                        'kg_par_scan': kg_scan,
                        'seuil': 0.3,
                        'bac_code': col.bac.code,
                    },
                    'date': d,
                })

        # 2. Comptes en attente (compte_en_attente) — Personnel en attente, Admin uniquement (OpenAPI 1.3.0)
        if not is_referent and (not type_filter or type_filter == 'compte_en_attente'):
            comptes_qs = Utilisateur.objects.filter(
                role__in=[Role.OPERATEUR_TRI, Role.RESPONSABLE_METHANISATION],
                statut_validation=StatutValidation.EN_ATTENTE
            )

            for u in comptes_qs:
                d = u.date_inscription or u.date_creation
                elements.append({
                    'type': 'compte_en_attente',
                    'objet_type': TypeObjet.UTILISATEUR,
                    'objet_id': str(u.id),
                    'libelle': f"{u.nom} ({u.telephone}) — Personnel {u.role} en attente de validation",
                    'details': {
                        'telephone': u.telephone,
                        'email': u.email,
                        'nom': u.nom,
                        'role': u.role,
                    },
                    'date': d,
                })

        # 3. Scans hors zone (scan_hors_zone)
        if not type_filter or type_filter == 'scan_hors_zone':
            scans_hz_qs = Scan.objects.filter(
                statut=StatutScan.HORS_ZONE
            ).select_related('citoyen', 'bac')
            if is_referent:
                scans_hz_qs = scans_hz_qs.filter(bac=ref_bac) if ref_bac else scans_hz_qs.none()

            for sc in scans_hz_qs:
                dist = float(sc.distance_m or 0)
                elements.append({
                    'type': 'scan_hors_zone',
                    'objet_type': 'scan',
                    'objet_id': str(sc.id),
                    'libelle': f"Scan hors zone par {sc.citoyen.nom} pour {sc.bac.code} ({dist:.0f} m)",
                    'details': {
                        'distance_m': dist,
                        'citoyen': sc.citoyen.nom,
                        'bac_code': sc.bac.code,
                        'seuil_m': 100,
                    },
                    'date': sc.horodatage,
                })

        # 4. Scans non localisés (scan_non_localise)
        if not type_filter or type_filter == 'scan_non_localise':
            scans_nl_qs = Scan.objects.filter(
                statut=StatutScan.NON_LOCALISE
            ).select_related('citoyen', 'bac')
            if is_referent:
                scans_nl_qs = scans_nl_qs.filter(bac=ref_bac) if ref_bac else scans_nl_qs.none()

            for sc in scans_nl_qs:
                elements.append({
                    'type': 'scan_non_localise',
                    'objet_type': 'scan',
                    'objet_id': str(sc.id),
                    'libelle': f"Scan non localisé par {sc.citoyen.nom} pour {sc.bac.code}",
                    'details': {
                        'citoyen': sc.citoyen.nom,
                        'bac_code': sc.bac.code,
                    },
                    'date': sc.horodatage,
                })

        # 5. Bacs surinscrits (bac_surinscrit)
        if not type_filter or type_filter == 'bac_surinscrit':
            bacs_qs = Bac.objects.all()
            if is_referent:
                bacs_qs = bacs_qs.filter(id=ref_bac.id) if ref_bac else bacs_qs.none()

            for b in bacs_qs:
                nb_valides = b.utilisateurs.filter(statut_validation=StatutValidation.VALIDE).count()
                if nb_valides > b.nb_foyers_declares:
                    dernier_inscrit = b.utilisateurs.filter(
                        statut_validation=StatutValidation.VALIDE
                    ).order_by('-date_creation').first()
                    d = dernier_inscrit.date_creation if dernier_inscrit else timezone.now()

                    elements.append({
                        'type': 'bac_surinscrit',
                        'objet_type': TypeObjet.BAC,
                        'objet_id': str(b.id),
                        'libelle': f"{b.code} ({b.residence}) : {nb_valides} citoyens validés pour {b.nb_foyers_declares} foyers déclarés",
                        'details': {
                            'nb_citoyens_valides': nb_valides,
                            'nb_foyers_declares': b.nb_foyers_declares,
                            'bac_code': b.code,
                            'residence': b.residence,
                        },
                        'date': d,
                    })

        # Tri du plus ancien au plus récent
        elements.sort(key=lambda item: item['date'] or timezone.now())

        serializer = ElementVerificationSerializer(elements, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ParametreListView(generics.ListAPIView):
    """
    GET /api/v1/parametres/
    Table complète des paramètres système (non paginée).
    """
    queryset = Parametre.objects.all().order_by('cle')
    serializer_class = ParametreSerializer
    permission_classes = [EstAdmin]
    pagination_class = None


class ParametreDetailUpdateView(APIView):
    """
    PATCH /api/v1/parametres/{cle}/
    Mise à jour d'un paramètre système (administrateur).
    Enregistre l'ancienne et la nouvelle valeur dans JournalAudit.
    """
    permission_classes = [EstAdmin]

    @transaction.atomic
    def patch(self, request, cle):
        parametre = get_object_or_404(Parametre.objects.select_for_update(), cle=cle)
        serializer = ParametreUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ancienne_valeur = float(parametre.valeur)
        nouvelle_valeur = serializer.validated_data['valeur']
        motif = serializer.validated_data.get('motif', "Modification du paramètre système par l'administrateur")

        if parametre.cle == 'validation_comptes_personnel':
            try:
                val_dec = Decimal(str(nouvelle_valeur))
                if val_dec not in (Decimal('0'), Decimal('1')):
                    raise ValueError()
            except (ValueError, TypeError):
                raise MetierException(
                    code="PARAMETRE_INVALIDE",
                    message="La valeur du paramètre 'validation_comptes_personnel' doit être 0 ou 1.",
                    details={"valeur": float(nouvelle_valeur)}
                )

        parametre.valeur = nouvelle_valeur
        parametre.date_modification = timezone.now()
        parametre.save()

        JournalAudit.objects.create(
            auteur=request.user,
            action="parametre.modifier",
            objet_type=TypeObjet.PARAMETRE,
            objet_id=parametre.cle,
            ancienne_valeur=json.dumps(ancienne_valeur),
            nouvelle_valeur=json.dumps(float(nouvelle_valeur)),
            motif=motif
        )

        return Response(
            ParametreSerializer(parametre).data,
            status=status.HTTP_200_OK
        )


class JournalAuditListView(generics.ListAPIView):
    """
    GET /api/v1/journal/
    Journal d'audit immuable (administrateur).
    Filtres : objet_type, objet_id, auteur_id.
    Paginé de la plus récente à la plus ancienne entrée.
    """
    serializer_class = EntreeJournalSerializer
    permission_classes = [EstAdmin]

    def get_queryset(self):
        queryset = JournalAudit.objects.all().select_related('auteur').order_by('-date')
        objet_type = self.request.query_params.get('objet_type')
        if objet_type:
            queryset = queryset.filter(objet_type=objet_type)
        objet_id = self.request.query_params.get('objet_id')
        if objet_id:
            queryset = queryset.filter(objet_id=objet_id)
        auteur_id = self.request.query_params.get('auteur_id')
        if auteur_id:
            queryset = queryset.filter(auteur_id=auteur_id)
        return queryset


class BacTracabiliteView(APIView):
    """
    GET /api/v1/bacs/{id}/tracabilite/
    Historique complet d'un bac (Écran de traçabilité du Control Center).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        bac = get_object_or_404(Bac, id=id)
        if not (
            request.user.is_superuser
            or request.user.role == Role.ADMINISTRATEUR
            or (request.user.role == Role.REFERENT and request.user.bac_id == bac.id)
        ):
            raise PermissionDenied("La traçabilité détaillée est réservée à l'administrateur et au référent du bac")

        citoyens_qs = bac.utilisateurs.all()
        citoyens_data = [
            {
                'id': u.id,
                'nom': u.nom,
                'statut_validation': u.statut_validation,
            }
            for u in citoyens_qs
        ]

        collectes_qs = Collecte.objects.filter(bac=bac).select_related(
            'tournee', 'tournee__site', 'tournee__collecteur'
        ).order_by('-date_ouverture')

        historique = []
        for col in collectes_qs:
            tournee = col.tournee
            lots_qs = LotTrie.objects.filter(tournee=tournee)
            lots_data = LotTrieSerializer(lots_qs, many=True).data

            tx_qs = GreenPointsTransaction.objects.filter(collecte=col)
            tx_data = GreenPointsTransactionSerializer(tx_qs, many=True).data

            prod_data = None
            if tournee.site:
                prod = ProductionEnergie.objects.filter(site=tournee.site, date=tournee.date).first()
                if prod:
                    prod_data = ProductionEnergieSerializer(prod).data

            first_tx = tx_qs.first()
            if first_tx:
                valeur_kg = float(first_tx.valeur_kg) if first_tx.valeur_kg is not None else None
                coef_qualite = float(first_tx.coef_qualite) if first_tx.coef_qualite is not None else None
            else:
                valeur_kg = None
                coef_qualite = None

            points_bac = None
            if col.poids_net_kg is not None and valeur_kg is not None and coef_qualite is not None:
                points_bac = round(float(col.poids_net_kg) * valeur_kg * coef_qualite, 2)

            historique.append({
                'collecte': CollecteSerializer(col).data,
                'tournee': TourneeSerializer(tournee).data,
                'lots': lots_data,
                'valeur_kg': valeur_kg,
                'coef_qualite': coef_qualite,
                'points_bac': points_bac,
                'transactions': tx_data,
                'production': prod_data,
            })

        bac_data = BacSerializer(bac).data
        payload = {
            'bac': bac_data,
            'citoyens': citoyens_data,
            'historique': historique,
        }
        return Response(payload, status=status.HTTP_200_OK)

