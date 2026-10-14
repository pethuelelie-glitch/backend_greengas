from django.contrib import admin
from apps.simulateur.models import ScenarioSimulation


@admin.register(ScenarioSimulation)
class ScenarioSimulationAdmin(admin.ModelAdmin):
    list_display = ('site', 'facteur_mesure', 'date_modification', 'date_creation')
    search_fields = ('site__code', 'site__nom')
    ordering = ('site__code',)
