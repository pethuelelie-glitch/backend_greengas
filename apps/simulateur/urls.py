from django.urls import path
from apps.simulateur.views import (
    ScenarioSimulationListCreateView,
    ScenarioSimulationDeleteView,
)

urlpatterns = [
    # Scénarios de simulation (/api/v1/simulation/scenarios/...)
    path('simulation/scenarios/', ScenarioSimulationListCreateView.as_view(), name='simulation_scenarios_list_create'),
    path('simulation/scenarios/<uuid:site_id>/', ScenarioSimulationDeleteView.as_view(), name='simulation_scenarios_delete'),
]
