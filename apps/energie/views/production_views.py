import json
from decimal import Decimal
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.energie.models import (
    ProductionEnergie,
    Alerte,
    StatutJournee,
    TypeAlerte,
    StatutAlerte,
)
from apps.energie.serializers import (
    ProductionEnergieSerializer,
    ProductionGlobaleSerializer,
    MesureSiteSerializer,
    ClotureProductionSerializer,
)
from apps.referentiel.models import Site
from apps.supervision.models import JournalAudit, TypeObjet
from apps.comptes.models import Role
from apps.comptes.permissions import EstAdminOuResponsable
from apps.comptes.exceptions import MetierException


class EstCapteurOuAdmin(permissions.BasePermission):
    """Autorise les comptes capteur IoT et les administrateurs"""
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and
            (request.user.role in [Role.CAPTEUR, Role.ADMINISTRATEUR] or request.user.is_superuser)
        )


class ProductionListView(generics.ListAPIView):
    """
    GET /api/v1/productions/
    Liste paginée des productions journalières avec filtres site_id, date_debut, date_fin.
    """
    serializer_class = ProductionEnergieSerializer
    permission_classes = [EstAdminOuResponsable]

    def get_queryset(self):
        queryset = ProductionEnergie.objects.all().select_related('site').order_by('-date', 'site__code')
        site_id = self.request.query_params.get('site_id')
        if site_id:
            queryset = queryset.filter(site_id=site_id)
        date_debut = self.request.query_params.get('date_debut')
        if date_debut:
            queryset = queryset.filter(date__gte=date_debut)
        date_fin = self.request.query_params.get('date_fin')
        if date_fin:
            queryset = queryset.filter(date__lte=date_fin)
        return queryset


class ProductionGlobaleView(APIView):
    """
    GET /api/v1/productions/globale/
    Agrégat de production de tous les sites pour une date donnée.
    """
    permission_classes = [EstAdminOuResponsable]

    def get(self, request):
        date_str = request.query_params.get('date')
        if not date_str:
            raise MetierException(
                code="VALIDATION",
                message="Le paramètre date est obligatoire (format AAAA-MM-JJ).",
                details={"date": ["Ce paramètre de requête est obligatoire."]},
                status_code=status.HTTP_400_BAD_REQUEST
            )

        productions = list(
            ProductionEnergie.objects.filter(date=date_str).select_related('site').order_by('site__code')
        )
        total_sites = Site.objects.count()

        poids_organique_recu_kg = sum(
            p.poids_organique_recu_kg or Decimal('0.00') for p in productions
        )
        biogaz_attendu_m3 = sum(
            p.biogaz_attendu_m3 or Decimal('0.00') for p in productions
        )
        biogaz_mesure_m3 = sum(
            p.biogaz_mesure_m3 or Decimal('0.00') for p in productions
        )
        electricite_kwh = sum(
            p.electricite_kwh or Decimal('0.00') for p in productions
        )
        chaleur_kwh = sum(
            p.chaleur_kwh or Decimal('0.00') for p in productions
        )
        digestat_kg = sum(
            p.digestat_kg or Decimal('0.00') for p in productions
        )
        foyers_equivalents = sum(
            p.foyers_equivalents or Decimal('0.00') for p in productions
        )
        alertes_ouvertes = Alerte.objects.filter(statut=StatutAlerte.OUVERTE).count()

        donnees = {
            'date': date_str,
            'nb_sites': total_sites,
            'poids_organique_recu_kg': poids_organique_recu_kg,
            'biogaz_attendu_m3': biogaz_attendu_m3,
            'biogaz_mesure_m3': biogaz_mesure_m3,
            'electricite_kwh': electricite_kwh,
            'chaleur_kwh': chaleur_kwh,
            'digestat_kg': digestat_kg,
            'foyers_equivalents': foyers_equivalents,
            'alertes_ouvertes': alertes_ouvertes,
            'par_site': productions,
        }

        serializer = ProductionGlobaleSerializer(donnees)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ProductionDetailView(generics.RetrieveAPIView):
    """
    GET /api/v1/productions/{id}/
    Détail d'une production journalière par UUID.
    """
    queryset = ProductionEnergie.objects.all().select_related('site')
    serializer_class = ProductionEnergieSerializer
    permission_classes = [EstAdminOuResponsable]
    lookup_field = 'id'


class ProductionCloturerView(APIView):
    """
    POST /api/v1/productions/{id}/cloturer/
    Clôturer la journée d'un site (responsable méthanisation ou admin).
    Destination du digestat obligatoire.
    Renvoie 422 JOURNEE_CLOTUREE si déjà clôturée.
    """
    permission_classes = [EstAdminOuResponsable]

    @transaction.atomic
    def post(self, request, id):
        production = get_object_or_404(
            ProductionEnergie.objects.select_for_update(), id=id
        )

        if production.statut_journee == StatutJournee.CLOTUREE:
            raise MetierException(
                code="JOURNEE_CLOTUREE",
                message="Cette journée de production est déjà clôturée.",
                details={"statut_journee": production.statut_journee}
            )

        serializer = ClotureProductionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ancienne_valeur = json.dumps({
            "statut_journee": production.statut_journee,
            "destination_digestat": production.destination_digestat
        })

        production.destination_digestat = serializer.validated_data['destination_digestat']
        production.statut_journee = StatutJournee.CLOTUREE
        production.save()

        nouvelle_valeur = json.dumps({
            "statut_journee": production.statut_journee,
            "destination_digestat": production.destination_digestat
        })

        JournalAudit.objects.create(
            auteur=request.user,
            action="production.cloturer",
            objet_type=TypeObjet.PRODUCTION,
            objet_id=str(production.id),
            ancienne_valeur=ancienne_valeur,
            nouvelle_valeur=nouvelle_valeur,
            motif=f"Clôture journée {production.date} site {production.site.code}"
        )

        return Response(
            ProductionEnergieSerializer(production).data,
            status=status.HTTP_200_OK
        )


class SiteMesuresView(APIView):
    """
    POST /api/v1/sites/{id}/mesures/
    Envoyer la mesure journalière du site (capteur ou simulateur).
    Met à jour la ProductionEnergie : écart %, électricité (kWh), chaleur (kWh), digestat (kg), foyers équivalents.
    Déclenche / met à jour des alertes si |écart| >= 20 % ou CH4 < 50 %.
    Journalisé dans JournalAudit.
    """
    permission_classes = [EstCapteurOuAdmin]

    @transaction.atomic
    def post(self, request, id):
        site = get_object_or_404(Site, id=id)
        serializer = MesureSiteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        date = data['date']
        biogaz_mesure = data['biogaz_mesure_m3']
        ch4_pct = data['ch4_pct']
        temperature_c = data.get('temperature_c')
        ph = data.get('ph')
        source = data['source']

        production, created = ProductionEnergie.objects.get_or_create(
            site=site,
            date=date,
            defaults={
                'poids_organique_recu_kg': Decimal('0.00'),
                'biogaz_attendu_m3': Decimal('0.00'),
            }
        )
        production = ProductionEnergie.objects.select_for_update().get(pk=production.pk)

        # Si le biogaz attendu n'était pas calculé mais que des matières organiques ont été reçues
        if production.biogaz_attendu_m3 == Decimal('0.00') and production.poids_organique_recu_kg > Decimal('0.00'):
            production.biogaz_attendu_m3 = round(production.poids_organique_recu_kg * Decimal('0.10'), 2)

        # Calcul de l'écart (%)
        if production.biogaz_attendu_m3 > Decimal('0.00'):
            ecart = ((biogaz_mesure - production.biogaz_attendu_m3) / production.biogaz_attendu_m3) * Decimal('100')
            ecart_pct = Decimal(str(round(ecart, 1)))
        else:
            ecart_pct = Decimal('0.0')

        # Formules métier officielles
        electricite_kwh = Decimal(str(round(biogaz_mesure * Decimal('1.7'), 2)))
        chaleur_kwh = Decimal(str(round(biogaz_mesure * Decimal('3.4'), 2)))
        poids_org = production.poids_organique_recu_kg or Decimal('0.00')
        digestat_kg = Decimal(str(round(poids_org * Decimal('0.5'), 2)))
        foyers_equivalents = Decimal(str(round(electricite_kwh * Decimal('365') / Decimal('1785'), 2)))

        badge_source = 'mesure' if source == 'capteur' else 'simule'

        # Mise à jour de la production
        production.biogaz_mesure_m3 = biogaz_mesure
        production.ch4_pct = ch4_pct
        production.temperature_c = temperature_c
        production.ph = ph
        production.ecart_pct = ecart_pct
        production.biogaz_cuisson_m3 = Decimal('0.00')
        production.biogaz_perte_m3 = Decimal('0.00')
        production.biogaz_valorise_m3 = biogaz_mesure
        production.electricite_kwh = electricite_kwh
        production.chaleur_kwh = chaleur_kwh
        production.digestat_kg = digestat_kg
        production.foyers_equivalents = foyers_equivalents
        production.foyers_cuisson = Decimal('0.00')
        production.statuts_donnees = {
            'poids_organique_recu_kg': 'mesure' if poids_org > 0 else 'estime',
            'biogaz_attendu_m3': 'estime',
            'biogaz_mesure_m3': badge_source,
            'ch4_pct': badge_source,
            'electricite_kwh': 'estime',
            'chaleur_kwh': 'estime',
            'digestat_kg': 'estime',
            'foyers_equivalents': 'estime',
        }
        production.save()

        a_declenche_alerte = False

        # Vérification Alerte 1 : Écart de production (|écart| >= 20 %)
        if production.biogaz_attendu_m3 > Decimal('0.00') and abs(ecart_pct) >= Decimal('20.0'):
            a_declenche_alerte = True
            desc_prod = (
                f"Production de biogaz inférieure de {abs(ecart_pct):.0f} % à l'attendu"
                if ecart_pct < 0
                else f"Production de biogaz supérieure de {abs(ecart_pct):.0f} % à l'attendu"
            )
            alerte_prod = Alerte.objects.filter(
                site=site,
                type=TypeAlerte.PRODUCTION,
                statut=StatutAlerte.OUVERTE
            ).first()

            if alerte_prod:
                alerte_prod.nb_occurrences += 1
                alerte_prod.valeur_attendue = production.biogaz_attendu_m3
                alerte_prod.valeur_mesuree = biogaz_mesure
                alerte_prod.ecart_pct = ecart_pct
                alerte_prod.description = desc_prod
                alerte_prod.date_derniere_occurrence = timezone.now()
                alerte_prod.save()

                # Notification alerte_repetee (Contrat 1.4.0)
                try:
                    from apps.comptes.models import Role, Utilisateur
                    from apps.supervision.models import TypeNotification, NiveauNotification
                    from apps.supervision.services import notifier_utilisateurs
                    dest = Utilisateur.objects.filter(role=Role.RESPONSABLE_METHANISATION, actif=True, statut_validation='valide')
                    notifier_utilisateurs(
                        destinataires=dest,
                        type=TypeNotification.ALERTE_REPETEE,
                        niveau=NiveauNotification.ATTENTION,
                        titre="Alerte répétée",
                        message=f"{site.code} : l'écart continue ({alerte_prod.nb_occurrences} jours).",
                        objet_type="alerte",
                        objet_id=alerte_prod.id,
                        auteur=request.user
                    )
                except Exception:
                    pass
            else:
                alerte_prod = Alerte.objects.create(
                    site=site,
                    type=TypeAlerte.PRODUCTION,
                    statut=StatutAlerte.OUVERTE,
                    valeur_attendue=production.biogaz_attendu_m3,
                    valeur_mesuree=biogaz_mesure,
                    ecart_pct=ecart_pct,
                    description=desc_prod,
                    nb_occurrences=1
                )

                # Notification alerte_ouverte (Contrat 1.4.0)
                try:
                    from apps.comptes.models import Role, Utilisateur
                    from apps.supervision.models import TypeNotification, NiveauNotification
                    from apps.supervision.services import notifier_utilisateurs
                    dest = Utilisateur.objects.filter(role__in=[Role.RESPONSABLE_METHANISATION, Role.ADMINISTRATEUR], actif=True, statut_validation='valide')
                    signe = f"{ecart_pct:.0f} %" if ecart_pct < 0 else f"+{ecart_pct:.0f} %"
                    notifier_utilisateurs(
                        destinataires=dest,
                        type=TypeNotification.ALERTE_OUVERTE,
                        niveau=NiveauNotification.CRITIQUE,
                        titre="Alerte ouverte",
                        message=f"{site.code} : biogaz {signe} ({biogaz_mesure} m³ pour {production.biogaz_attendu_m3} m³ attendus).",
                        objet_type="alerte",
                        objet_id=alerte_prod.id,
                        auteur=request.user
                    )
                except Exception:
                    pass

        # Vérification Alerte 2 : Teneur en CH4 < 50 %
        if ch4_pct < Decimal('50.0'):
            a_declenche_alerte = True
            seuil_ch4 = Decimal('50.0')
            ecart_ch4 = Decimal(str(round(((ch4_pct - seuil_ch4) / seuil_ch4) * Decimal('100'), 1)))
            desc_ch4 = f"Teneur en CH₄ ({ch4_pct} %) inférieure au seuil minimal de 50 %"
            alerte_comp = Alerte.objects.filter(
                site=site,
                type=TypeAlerte.COMPOSITION,
                statut=StatutAlerte.OUVERTE
            ).first()

            if alerte_comp:
                alerte_comp.nb_occurrences += 1
                alerte_comp.valeur_attendue = seuil_ch4
                alerte_comp.valeur_mesuree = ch4_pct
                alerte_comp.ecart_pct = ecart_ch4
                alerte_comp.description = desc_ch4
                alerte_comp.date_derniere_occurrence = timezone.now()
                alerte_comp.save()

                # Notification alerte_repetee (Contrat 1.4.0)
                try:
                    from apps.comptes.models import Role, Utilisateur
                    from apps.supervision.models import TypeNotification, NiveauNotification
                    from apps.supervision.services import notifier_utilisateurs
                    dest = Utilisateur.objects.filter(role=Role.RESPONSABLE_METHANISATION, actif=True, statut_validation='valide')
                    notifier_utilisateurs(
                        destinataires=dest,
                        type=TypeNotification.ALERTE_REPETEE,
                        niveau=NiveauNotification.ATTENTION,
                        titre="Alerte répétée",
                        message=f"{site.code} : teneur CH₄ basse ({ch4_pct} %, {alerte_comp.nb_occurrences} occurrences).",
                        objet_type="alerte",
                        objet_id=alerte_comp.id,
                        auteur=request.user
                    )
                except Exception:
                    pass
            else:
                alerte_comp = Alerte.objects.create(
                    site=site,
                    type=TypeAlerte.COMPOSITION,
                    statut=StatutAlerte.OUVERTE,
                    valeur_attendue=seuil_ch4,
                    valeur_mesuree=ch4_pct,
                    ecart_pct=ecart_ch4,
                    description=desc_ch4,
                    nb_occurrences=1
                )

                # Notification alerte_ouverte (Contrat 1.4.0)
                try:
                    from apps.comptes.models import Role, Utilisateur
                    from apps.supervision.models import TypeNotification, NiveauNotification
                    from apps.supervision.services import notifier_utilisateurs
                    dest = Utilisateur.objects.filter(role__in=[Role.RESPONSABLE_METHANISATION, Role.ADMINISTRATEUR], actif=True, statut_validation='valide')
                    notifier_utilisateurs(
                        destinataires=dest,
                        type=TypeNotification.ALERTE_OUVERTE,
                        niveau=NiveauNotification.CRITIQUE,
                        titre="Alerte ouverte",
                        message=f"{site.code} : teneur CH₄ critique ({ch4_pct} % < 50 %).",
                        objet_type="alerte",
                        objet_id=alerte_comp.id,
                        auteur=request.user
                    )
                except Exception:
                    pass

        if a_declenche_alerte and site.statut != 'alerte':
            site.statut = 'alerte'
            site.save()

        # Enregistrement dans JournalAudit
        JournalAudit.objects.create(
            auteur=request.user,
            action="site.mesures",
            objet_type=TypeObjet.PRODUCTION,
            objet_id=str(production.id),
            ancienne_valeur=None,
            nouvelle_valeur=json.dumps({
                "biogaz_mesure_m3": float(biogaz_mesure),
                "ch4_pct": float(ch4_pct),
                "temperature_c": float(temperature_c) if temperature_c is not None else None,
                "ph": float(ph) if ph is not None else None,
                "electricite_kwh": float(electricite_kwh),
                "chaleur_kwh": float(chaleur_kwh),
                "digestat_kg": float(digestat_kg),
                "foyers_equivalents": float(foyers_equivalents),
                "ecart_pct": float(ecart_pct),
                "source": source
            }),
            motif=f"Mesure journalière {source} pour site {site.code}"
        )

        return Response(
            ProductionEnergieSerializer(production).data,
            status=status.HTTP_200_OK
        )
