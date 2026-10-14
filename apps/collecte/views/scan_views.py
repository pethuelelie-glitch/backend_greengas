import datetime
from decimal import Decimal

from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.collecte.models import Scan, StatutScan
from apps.collecte.serializers import ScanSerializer, ScanRequeteSerializer
from apps.collecte.utils import calculer_distance_haversine, get_parametre
from apps.comptes.exceptions import MetierException
from apps.comptes.models import Role, StatutValidation
from apps.referentiel.models import Bac


class ScanListCreateView(generics.ListCreateAPIView):
    """
    GET /api/v1/scans/ — Liste des scans (le citoyen ne voit que les siens).
    POST /api/v1/scans/ — Scan du QR code d'un bac par un citoyen.
    """
    serializer_class = ScanSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == Role.ADMINISTRATEUR or user.is_superuser:
            queryset = Scan.objects.all()
        elif user.role == Role.CITOYEN:
            queryset = Scan.objects.filter(citoyen=user)
        elif user.role == Role.REFERENT and user.bac_id:
            queryset = Scan.objects.filter(bac_id=user.bac_id)
        elif user.role == Role.COLLECTEUR:
            queryset = Scan.objects.filter(bac__collectes__collecteur=user).distinct()
        else:
            queryset = Scan.objects.none()

        citoyen_id = self.request.query_params.get('citoyen_id')
        if citoyen_id and (user.role == Role.ADMINISTRATEUR or user.is_superuser):
            queryset = queryset.filter(citoyen_id=citoyen_id)

        bac_id = self.request.query_params.get('bac_id')
        if bac_id:
            queryset = queryset.filter(bac_id=bac_id)

        statut = self.request.query_params.get('statut')
        if statut:
            queryset = queryset.filter(statut=statut)

        date_debut = self.request.query_params.get('date_debut')
        if date_debut:
            queryset = queryset.filter(horodatage__gte=date_debut)

        date_fin = self.request.query_params.get('date_fin')
        if date_fin:
            queryset = queryset.filter(horodatage__lte=date_fin)

        return queryset.order_by('-horodatage')

    def create(self, request, *args, **kwargs):
        # 1. Vérification du rôle et du statut de validation du compte
        if request.user.role != Role.CITOYEN and not request.user.is_superuser:
            raise MetierException(
                code="ROLE_INVALIDE",
                message="Seuls les citoyens peuvent scanner un bac",
                status_code=status.HTTP_403_FORBIDDEN
            )

        if not request.user.actif or request.user.statut_validation != StatutValidation.VALIDE:
            raise MetierException(
                code="COMPTE_NON_VALIDE",
                message="Ce compte est désactivé ou non validé.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
            )

        # 2. Validation de la charge utile
        serializer = ScanRequeteSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        code_bac = serializer.validated_data.get('code_bac')
        bac_id = serializer.validated_data.get('bac_id')
        latitude = serializer.validated_data.get('latitude')
        longitude = serializer.validated_data.get('longitude')

        # Trouver le bac ciblé
        bac = None
        if code_bac:
            bac = Bac.objects.filter(code=code_bac).first()
        elif bac_id:
            bac = Bac.objects.filter(id=bac_id).first()
        elif getattr(request.user, 'bac', None):
            bac = request.user.bac

        if not bac:
            raise MetierException(
                code="BAC_INTROUVABLE",
                message="Le bac spécifié est introuvable",
                status_code=status.HTTP_404_NOT_FOUND
            )

        # 3. Anti-rebond (Debounce) : même citoyen + bac en moins de 10 secondes
        seuil_debounce = timezone.now() - datetime.timedelta(seconds=10)
        scan_recent = Scan.objects.filter(
            citoyen=request.user,
            bac=bac,
            horodatage__gte=seuil_debounce
        ).order_by('-horodatage').first()

        if scan_recent:
            return Response(ScanSerializer(scan_recent).data, status=status.HTTP_200_OK)

        # 4. Géolocalisation et calcul de la distance Haversine
        distance_m = None
        if latitude is None or longitude is None:
            # Pas de coordonnées GPS : scan non localisé (compte toujours)
            initial_statut = StatutScan.NON_LOCALISE
        else:
            dist_calculee = calculer_distance_haversine(
                latitude, longitude,
                bac.latitude, bac.longitude
            )
            distance_m = round(Decimal(str(dist_calculee)), 2)
            rayon_scan_m = get_parametre('rayon_scan_m', 100.0)

            if dist_calculee > rayon_scan_m:
                initial_statut = StatutScan.HORS_ZONE
            else:
                initial_statut = StatutScan.VALIDE

        # 5. Plafond journalier (max 2 scans valides par jour par citoyen)
        today = timezone.now().date()
        max_scans_par_jour = int(get_parametre('max_scans_par_jour', 2))

        if initial_statut == StatutScan.HORS_ZONE:
            statut_final = StatutScan.HORS_ZONE
            compte = False
        else:
            # Compter les scans valides d'aujourd'hui qui comptent
            scans_valides_aujourdhui = Scan.objects.filter(
                citoyen=request.user,
                horodatage__date=today,
                compte=True
            ).count()

            if scans_valides_aujourdhui >= max_scans_par_jour:
                statut_final = StatutScan.REFUSE_PLAFOND
                compte = False
            else:
                statut_final = initial_statut
                compte = True

        # 6. Création de l'enregistrement de scan
        scan = Scan.objects.create(
            citoyen=request.user,
            bac=bac,
            latitude=latitude,
            longitude=longitude,
            distance_m=distance_m,
            statut=statut_final,
            compte=compte
        )

        return Response(ScanSerializer(scan).data, status=status.HTTP_201_CREATED)
