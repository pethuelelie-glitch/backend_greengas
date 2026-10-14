import json
import math
from decimal import Decimal

from django.db import transaction, models
from django.db.models import Sum
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.collecte.models import (
    Tournee, StatutTournee, NiveauContamination,
    Collecte, StatutCollecte, StatutControle,
    Scan, StatutScan
)
from apps.comptes.exceptions import MetierException, ConflitException
from apps.comptes.models import Role
from apps.comptes.permissions import EstOperateurTri, EstAdmin
from apps.energie.models import ProductionEnergie, StatutJournee
from apps.greenpoints.models import GreenPointsTransaction, StatutTransaction
from apps.supervision.models import JournalAudit, TypeObjet
from apps.tri.models import (
    LotTrie, Categorie, Destination,
    DESTINATION_PAR_CATEGORIE
)
from apps.tri.serializers import (
    LotTrieSerializer,
    TriRequeteSerializer,
    ResultatTriSerializer,
)
from apps.tri.utils import get_parametre, generer_code_lot


COEF_FILIERE_DEFAULTS = {
    Categorie.ORGANIQUE: ('coefficient_filiere_organique', Decimal('10.0')),
    Categorie.METAL: ('coefficient_filiere_metal', Decimal('15.0')),
    Categorie.PLASTIQUE: ('coefficient_filiere_plastique', Decimal('8.0')),
    Categorie.BIOMASSE: ('coefficient_filiere_biomasse', Decimal('6.0')),
    Categorie.CARTON_PAPIER: ('coefficient_filiere_carton_papier', Decimal('5.0')),
    Categorie.VERRE: ('coefficient_filiere_verre', Decimal('3.0')),
    Categorie.REFUS: ('coefficient_filiere_refus', Decimal('0.0')),
}

QUALITE_DEFAULTS = {
    NiveauContamination.FAIBLE: ('coefficient_qualite_faible', Decimal('1.0')),
    NiveauContamination.MOYEN: ('coefficient_qualite_moyen', Decimal('0.8')),
    NiveauContamination.ELEVE: ('coefficient_qualite_eleve', Decimal('0.5')),
}


class TourneeTriView(APIView):
    """
    GET /api/v1/tournees/{id}/tri/ — Résultat du tri d'une tournée
    POST /api/v1/tournees/{id}/tri/ — Saisie et validation du tri par l'opérateur de tri
    """

    def get_permissions(self):
        return [(EstOperateurTri | EstAdmin)()]

    def get(self, request, id=None, pk=None):
        tournee_id = id or pk
        tournee = generics.get_object_or_404(Tournee, id=tournee_id)

        if tournee.statut != StatutTournee.TRIEE or not tournee.lots.exists():
            raise NotFound("Aucun résultat de tri disponible pour cette tournée")

        lots = list(tournee.lots.all())
        poids_trie_kg = sum(lot.poids_kg for lot in lots)

        poids_collecte_kg = tournee.collectes.filter(
            poids_net_kg__isnull=False
        ).aggregate(total=Sum('poids_net_kg'))['total'] or Decimal('0.00')

        if poids_collecte_kg > Decimal('0.00'):
            ecart_pct = (abs(poids_trie_kg - poids_collecte_kg) / poids_collecte_kg) * Decimal('100.0')
        else:
            ecart_pct = Decimal('0.00')

        niveau = tournee.niveau_contamination or NiveauContamination.FAIBLE
        param_qualite, def_qualite = QUALITE_DEFAULTS.get(niveau, ('coefficient_qualite_faible', Decimal('1.0')))
        coef_qualite = get_parametre(param_qualite, def_qualite)

        transactions = tournee.transactions_points.all()
        nb_transactions = transactions.count()
        points_credites = transactions.filter(statut=StatutTransaction.CREDITEE).aggregate(total=Sum('points'))['total'] or 0
        points_en_attente = transactions.filter(statut=StatutTransaction.EN_ATTENTE).aggregate(total=Sum('points'))['total'] or 0

        first_tx = transactions.first()
        if first_tx:
            valeur_kg = first_tx.valeur_kg
            date_validation = first_tx.date
        else:
            # Recalculer valeur_kg depuis les lots
            valeur_kg = Decimal('0.0000')
            if poids_trie_kg > Decimal('0.00'):
                for lot in lots:
                    part_f = lot.poids_kg / poids_trie_kg
                    param_fil, def_fil = COEF_FILIERE_DEFAULTS.get(lot.categorie, (f'coefficient_filiere_{lot.categorie}', Decimal('0.0')))
                    coef_f = get_parametre(param_fil, def_fil)
                    valeur_kg += part_f * coef_f
            date_validation = timezone.now()

        # Audit log ou auteur
        audit = JournalAudit.objects.filter(
            objet_type=TypeObjet.TOURNEE,
            objet_id=str(tournee.id),
            action="tournee.tri"
        ).first()

        motif_ecart = None
        if audit:
            valide_par_id = audit.auteur_id
            date_validation = audit.date
            motif_ecart = audit.motif if audit.motif != "Validation du tri de la tournée" else None
        else:
            valide_par_id = request.user.id

        production = ProductionEnergie.objects.filter(site=tournee.site, date=tournee.date).first()
        production_id = production.id if production else None

        resultat = {
            "tournee_id": tournee.id,
            "code_tournee": tournee.code,
            "niveau_contamination": tournee.niveau_contamination or NiveauContamination.FAIBLE,
            "coef_qualite": round(coef_qualite, 2),
            "poids_collecte_kg": round(poids_collecte_kg, 2),
            "poids_trie_kg": round(poids_trie_kg, 2),
            "ecart_pct": round(ecart_pct, 2),
            "motif_ecart": motif_ecart,
            "valeur_kg": round(valeur_kg, 4),
            "lots": LotTrieSerializer(lots, many=True).data,
            "nb_transactions": nb_transactions,
            "points_credites": points_credites,
            "points_en_attente": points_en_attente,
            "production_id": production_id,
            "date_validation": date_validation,
            "valide_par_id": valide_par_id,
        }

        return Response(ResultatTriSerializer(resultat).data, status=status.HTTP_200_OK)

    def post(self, request, id=None, pk=None):
        tournee_id = id or pk
        tournee = generics.get_object_or_404(Tournee, id=tournee_id)

        # 1. Vérification : tournée déjà triée
        if tournee.statut == StatutTournee.TRIEE or tournee.lots.exists():
            raise ConflitException(
                code="CONFLIT",
                message="Cette tournée a déjà été triée"
            )

        # 2. Vérification : statut de la tournée
        if tournee.statut != StatutTournee.COLLECTEE:
            raise MetierException(
                code="TOURNEE_STATUT_INVALIDE",
                message=f"La tournée doit être au statut '{StatutTournee.COLLECTEE}' pour être triée (statut actuel: '{tournee.statut}')"
            )

        # 3. Validation de la charge utile
        serializer = TriRequeteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        niveau_contamination = data['niveau_contamination']
        lots_data = data['lots']
        motif_ecart = data.get('motif_ecart')

        # 4. Calcul des poids et tolérance
        poids_trie = sum(Decimal(str(item['poids_kg'])) for item in lots_data)

        # Poids de collecte (somme des collectes validées de la tournée)
        collectes_validees = tournee.collectes.filter(
            statut=StatutCollecte.VALIDEE,
            poids_net_kg__isnull=False
        )
        poids_collecte = collectes_validees.aggregate(total=Sum('poids_net_kg'))['total']
        if poids_collecte is None:
            # Fallback si pas de statut validee strict mais des poids nets renseignés
            poids_collecte = tournee.collectes.filter(
                poids_net_kg__isnull=False
            ).aggregate(total=Sum('poids_net_kg'))['total'] or Decimal('0.00')

        if poids_collecte > Decimal('0.00'):
            ecart_pct = (abs(poids_trie - poids_collecte) / poids_collecte) * Decimal('100.0')
        else:
            ecart_pct = Decimal('0.00') if poids_trie == Decimal('0.00') else Decimal('100.00')

        tolerance_tri_pct = get_parametre('tolerance_tri_pct', Decimal('2.0'))
        if ecart_pct > tolerance_tri_pct and not motif_ecart:
            raise MetierException(
                code="ECART_TOLERANCE",
                message=f"L'écart de pesée ({float(ecart_pct):.2f}%) dépasse la tolérance autorisée ({float(tolerance_tri_pct):.2f}%) sans motif d'écart renseigné",
                details={"ecart_pct": round(float(ecart_pct), 2)}
            )

        # 5. Transaction atomique pour exécuter l'ensemble du pipeline
        with transaction.atomic():
            # A. Création des LotTrie pour chaque catégorie
            lots_crees = []
            for item in lots_data:
                cat = item['categorie']
                poids = Decimal(str(item['poids_kg']))
                part_pct = round((poids / poids_trie * Decimal('100.0')), 2) if poids_trie > Decimal('0.00') else Decimal('0.00')
                dest = DESTINATION_PAR_CATEGORIE.get(cat, Destination.ENFOUISSEMENT)
                site_lot = tournee.site if cat == Categorie.ORGANIQUE else None
                code_lot = generer_code_lot(cat)

                lot = LotTrie.objects.create(
                    code_lot=code_lot,
                    tournee=tournee,
                    categorie=cat,
                    poids_kg=poids,
                    part_pct=part_pct,
                    destination=dest,
                    site=site_lot
                )
                lots_crees.append(lot)

            # B. Calcul de valeur_kg de la tournée
            valeur_kg = Decimal('0.0000')
            if poids_trie > Decimal('0.00'):
                for item in lots_data:
                    cat = item['categorie']
                    poids = Decimal(str(item['poids_kg']))
                    part_f = poids / poids_trie
                    param_fil, def_fil = COEF_FILIERE_DEFAULTS.get(cat, (f'coefficient_filiere_{cat}', Decimal('0.0')))
                    coef_f = get_parametre(param_fil, def_fil)
                    valeur_kg += part_f * coef_f
            valeur_kg = round(valeur_kg, 4)

            # C. Coefficient de qualité selon le niveau de contamination
            param_qual, def_qual = QUALITE_DEFAULTS.get(
                niveau_contamination,
                ('coefficient_qualite_faible', Decimal('1.0'))
            )
            coef_qualite = round(get_parametre(param_qual, def_qual), 2)

            # D. Distribution des GreenPoints par bac collecté
            collectes_a_traiter = tournee.collectes.filter(
                models.Q(statut=StatutCollecte.VALIDEE) | models.Q(poids_net_kg__isnull=False)
            ).select_related('bac')

            transactions_creees = []
            for collecte in collectes_a_traiter:
                poids_net = collecte.poids_net_kg or Decimal('0.00')
                points_bac = poids_net * valeur_kg * coef_qualite

                # Recherche des scans valides sur la période pour ce bac
                scans_bac_qs = Scan.objects.filter(bac=collecte.bac, compte=True)
                if collecte.date_validation:
                    prev_coll = Collecte.objects.filter(
                        bac=collecte.bac,
                        statut=StatutCollecte.VALIDEE,
                        date_validation__lt=collecte.date_validation
                    ).exclude(id=collecte.id).order_by('-date_validation').first()

                    scans_periode = scans_bac_qs.filter(horodatage__lte=collecte.date_validation)
                    if prev_coll and prev_coll.date_validation:
                        scans_periode = scans_periode.filter(horodatage__gt=prev_coll.date_validation)

                    if scans_periode.exists():
                        scans_bac_qs = scans_periode

                # Regrouper les scans par citoyen
                scans_par_citoyen = {}
                for s in scans_bac_qs:
                    scans_par_citoyen[s.citoyen_id] = scans_par_citoyen.get(s.citoyen_id, 0) + 1

                total_scans_bac = sum(scans_par_citoyen.values())
                if total_scans_bac > 0:
                    for citoyen_id, scans_citoyen in scans_par_citoyen.items():
                        ratio = Decimal(scans_citoyen) / Decimal(total_scans_bac)
                        poids_attribue = round(poids_net * ratio, 2)
                        pts_val = math.floor(float(points_bac * ratio))
                        statut_tx = (
                            StatutTransaction.CREDITEE
                            if collecte.statut_controle == StatutControle.NORMAL
                            else StatutTransaction.EN_ATTENTE
                        )

                        tx = GreenPointsTransaction.objects.create(
                            citoyen_id=citoyen_id,
                            bac=collecte.bac,
                            tournee=tournee,
                            collecte=collecte,
                            scans_citoyen=scans_citoyen,
                            scans_bac=total_scans_bac,
                            poids_attribue_kg=poids_attribue,
                            valeur_kg=valeur_kg,
                            coef_qualite=coef_qualite,
                            points=pts_val,
                            statut=statut_tx
                        )
                        transactions_creees.append(tx)

                        # Notification au citoyen (Contrat 1.4.0)
                        try:
                            from apps.supervision.models import TypeNotification, NiveauNotification
                            from apps.supervision.services import creer_notification
                            date_str = tournee.date.strftime('%d/%m')
                            if statut_tx == StatutTransaction.CREDITEE:
                                creer_notification(
                                    destinataire=tx.citoyen,
                                    type=TypeNotification.POINTS_CREDITES,
                                    niveau=NiveauNotification.INFO,
                                    titre="Points crédités",
                                    message=f"+{pts_val} points pour la collecte du {date_str} ({collecte.bac.code}).",
                                    objet_type="transaction",
                                    objet_id=tx.id,
                                    auteur=request.user
                                )
                            elif statut_tx == StatutTransaction.EN_ATTENTE:
                                creer_notification(
                                    destinataire=tx.citoyen,
                                    type=TypeNotification.POINTS_EN_ATTENTE,
                                    niveau=NiveauNotification.INFO,
                                    titre="Points en attente",
                                    message=f"{pts_val} points en attente de vérification ({collecte.bac.code}).",
                                    objet_type="transaction",
                                    objet_id=tx.id,
                                    auteur=request.user
                                )
                        except Exception:
                            pass

            # E. Mise à jour de la tournée
            tournee.statut = StatutTournee.TRIEE
            tournee.niveau_contamination = niveau_contamination
            tournee.save(update_fields=['statut', 'niveau_contamination'])

            # F. Création / mise à jour du bilan de production d'énergie
            poids_organique = next(
                (Decimal(str(item['poids_kg'])) for item in lots_data if item['categorie'] == Categorie.ORGANIQUE),
                Decimal('0.00')
            )
            production = None
            if tournee.site:
                production, _ = ProductionEnergie.objects.get_or_create(
                    site=tournee.site,
                    date=tournee.date,
                    defaults={
                        'statut_journee': StatutJournee.OUVERTE,
                        'poids_organique_recu_kg': Decimal('0.00'),
                        'biogaz_attendu_m3': Decimal('0.00'),
                    }
                )
                if poids_organique > Decimal('0.00'):
                    production.poids_organique_recu_kg = Decimal(str(production.poids_organique_recu_kg or 0)) + poids_organique
                    coef_biogaz = get_parametre('coefficient_biogaz_m3_par_kg', Decimal('0.1'))
                    production.biogaz_attendu_m3 = round(production.poids_organique_recu_kg * coef_biogaz, 2)
                    production.save(update_fields=['poids_organique_recu_kg', 'biogaz_attendu_m3'])

            # G. Enregistrement dans le journal d'audit
            JournalAudit.objects.create(
                auteur=request.user,
                action="tournee.tri",
                objet_type=TypeObjet.TOURNEE,
                objet_id=str(tournee.id),
                nouvelle_valeur=json.dumps({
                    "statut": StatutTournee.TRIEE,
                    "niveau_contamination": niveau_contamination,
                    "poids_trie_kg": float(poids_trie),
                    "nb_lots": len(lots_crees),
                }),
                motif=motif_ecart or "Validation du tri de la tournée"
            )

        now = timezone.now()
        points_credites = sum(tx.points for tx in transactions_creees if tx.statut == StatutTransaction.CREDITEE)
        points_en_attente = sum(tx.points for tx in transactions_creees if tx.statut == StatutTransaction.EN_ATTENTE)

        resultat = {
            "tournee_id": tournee.id,
            "code_tournee": tournee.code,
            "niveau_contamination": tournee.niveau_contamination,
            "coef_qualite": round(coef_qualite, 2),
            "poids_collecte_kg": round(poids_collecte, 2),
            "poids_trie_kg": round(poids_trie, 2),
            "ecart_pct": round(ecart_pct, 2),
            "motif_ecart": motif_ecart,
            "valeur_kg": round(valeur_kg, 4),
            "lots": LotTrieSerializer(lots_crees, many=True).data,
            "nb_transactions": len(transactions_creees),
            "points_credites": points_credites,
            "points_en_attente": points_en_attente,
            "production_id": production.id if production else None,
            "date_validation": now,
            "valide_par_id": request.user.id,
        }

        return Response(ResultatTriSerializer(resultat).data, status=status.HTTP_201_CREATED)


class LotListView(generics.ListAPIView):
    """
    GET /api/v1/lots/ — Lister les lots triés avec filtres
    Filtres : tournee_id, categorie, date_debut, date_fin
    """
    serializer_class = LotTrieSerializer
    permission_classes = [EstOperateurTri | EstAdmin]

    def get_queryset(self):
        queryset = LotTrie.objects.all().select_related('tournee', 'site')

        tournee_id = self.request.query_params.get('tournee_id')
        if tournee_id:
            queryset = queryset.filter(tournee_id=tournee_id)

        categorie = self.request.query_params.get('categorie')
        if categorie:
            queryset = queryset.filter(categorie=categorie)

        date_debut = self.request.query_params.get('date_debut')
        if date_debut:
            queryset = queryset.filter(tournee__date__gte=date_debut)

        date_fin = self.request.query_params.get('date_fin')
        if date_fin:
            queryset = queryset.filter(tournee__date__lte=date_fin)

        return queryset.order_by('-tournee__date', 'code_lot')
