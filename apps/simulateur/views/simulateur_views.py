from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.simulateur.models import ScenarioSimulation
from apps.simulateur.serializers import ScenarioSimulationSerializer
from apps.comptes.permissions import EstAdmin


class ScenarioSimulationListCreateView(APIView):
    """
    GET /api/v1/simulation/scenarios/ — Lister les scénarios de démo actifs (administrateur).
    POST /api/v1/simulation/scenarios/ — Forcer le facteur de mesure d'un site (administrateur).
    """
    permission_classes = [EstAdmin]

    def get(self, request):
        scenarios = ScenarioSimulation.objects.all().select_related('site').order_by('site__code')
        serializer = ScenarioSimulationSerializer(scenarios, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = ScenarioSimulationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        scenario = serializer.save()
        return Response(
            ScenarioSimulationSerializer(scenario).data,
            status=status.HTTP_201_CREATED
        )


class ScenarioSimulationDeleteView(APIView):
    """
    DELETE /api/v1/simulation/scenarios/{site_id}/ — Supprimer un scénario de démo (administrateur).
    Revient au fonctionnement nominal.
    """
    permission_classes = [EstAdmin]

    def delete(self, request, site_id):
        scenario = ScenarioSimulation.objects.filter(site_id=site_id).first()
        if scenario:
            scenario.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
