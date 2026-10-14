import json
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.energie.models import Alerte, StatutAlerte
from apps.energie.serializers import AlerteSerializer, ResoudreAlerteSerializer
from apps.supervision.models import JournalAudit, TypeObjet
from apps.comptes.permissions import EstAdminOuResponsable
from apps.comptes.exceptions import MetierException


class AlerteListView(generics.ListAPIView):
    """
    GET /api/v1/alertes/
    Liste paginée des alertes de performance, du plus récent au plus ancien.
    Filtres : site_id, statut, type.
    """
    serializer_class = AlerteSerializer
    permission_classes = [EstAdminOuResponsable]

    def get_queryset(self):
        queryset = Alerte.objects.all().select_related('site', 'resolue_par').order_by('-date_creation')
        site_id = self.request.query_params.get('site_id')
        if site_id:
            queryset = queryset.filter(site_id=site_id)
        statut = self.request.query_params.get('statut')
        if statut:
            queryset = queryset.filter(statut=statut)
        alerte_type = self.request.query_params.get('type')
        if alerte_type:
            queryset = queryset.filter(type=alerte_type)
        return queryset


class AlerteDetailView(generics.RetrieveAPIView):
    """
    GET /api/v1/alertes/{id}/
    Détail d'une alerte de performance.
    """
    queryset = Alerte.objects.all().select_related('site', 'resolue_par')
    serializer_class = AlerteSerializer
    permission_classes = [EstAdminOuResponsable]
    lookup_field = 'id'


class AlerteResoudreView(APIView):
    """
    POST /api/v1/alertes/{id}/resoudre/
    Marquer une alerte comme résolue (responsable méthanisation ou admin).
    Commentaire obligatoire. Journalisé dans JournalAudit.
    """
    permission_classes = [EstAdminOuResponsable]

    @transaction.atomic
    def post(self, request, id):
        alerte = get_object_or_404(Alerte.objects.select_for_update(), id=id)

        if alerte.statut == StatutAlerte.RESOLUE:
            raise MetierException(
                code="ALERTE_DEJA_RESOLUE",
                message="Cette alerte a déjà été résolue.",
                details={"statut": alerte.statut}
            )

        serializer = ResoudreAlerteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        commentaire = serializer.validated_data['commentaire']

        ancienne_valeur = json.dumps({
            "statut": alerte.statut,
            "commentaire_resolution": alerte.commentaire_resolution,
            "date_resolution": alerte.date_resolution.isoformat() if alerte.date_resolution else None
        })

        alerte.statut = StatutAlerte.RESOLUE
        alerte.commentaire_resolution = commentaire
        alerte.resolue_par = request.user
        alerte.date_resolution = timezone.now()
        alerte.save()

        # Si le site n'a plus d'alerte ouverte et était en statut 'alerte', repasser à 'nominal'
        site = alerte.site
        autres_alertes_ouvertes = Alerte.objects.filter(site=site, statut=StatutAlerte.OUVERTE).exists()
        if not autres_alertes_ouvertes and site.statut == 'alerte':
            site.statut = 'nominal'
            site.save()

        nouvelle_valeur = json.dumps({
            "statut": alerte.statut,
            "commentaire_resolution": alerte.commentaire_resolution,
            "date_resolution": alerte.date_resolution.isoformat() if alerte.date_resolution else None,
            "resolue_par_id": str(request.user.id)
        })

        JournalAudit.objects.create(
            auteur=request.user,
            action="alerte.resoudre",
            objet_type=TypeObjet.ALERTE,
            objet_id=str(alerte.id),
            ancienne_valeur=ancienne_valeur,
            nouvelle_valeur=nouvelle_valeur,
            motif=commentaire
        )

        return Response(
            AlerteSerializer(alerte).data,
            status=status.HTTP_200_OK
        )
