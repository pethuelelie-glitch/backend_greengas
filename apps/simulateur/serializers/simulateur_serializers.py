from decimal import Decimal
from rest_framework import serializers
from apps.simulateur.models import ScenarioSimulation
from apps.referentiel.models import Site


class ScenarioSimulationSerializer(serializers.ModelSerializer):
    site_id = serializers.PrimaryKeyRelatedField(
        queryset=Site.objects.all(),
        source='site'
    )
    facteur_mesure = serializers.DecimalField(
        max_digits=4,
        decimal_places=2,
        min_value=Decimal('0'),
        max_value=Decimal('2')
    )

    class Meta:
        model = ScenarioSimulation
        fields = ['site_id', 'facteur_mesure']

    def create(self, validated_data):
        site = validated_data['site']
        facteur_mesure = validated_data['facteur_mesure']
        scenario, _ = ScenarioSimulation.objects.update_or_create(
            site=site,
            defaults={'facteur_mesure': facteur_mesure}
        )
        return scenario
