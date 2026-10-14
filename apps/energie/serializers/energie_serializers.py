from decimal import Decimal
from rest_framework import serializers
from apps.energie.models import (
    ProductionEnergie,
    Alerte,
    StatutJournee,
    DestinationDigestat,
    TypeAlerte,
    StatutAlerte,
)


class ProductionEnergieSerializer(serializers.ModelSerializer):
    site_id = serializers.UUIDField(source='site.id', read_only=True)
    code_site = serializers.CharField(source='site.code', read_only=True)
    statuts_donnees = serializers.SerializerMethodField()

    class Meta:
        model = ProductionEnergie
        fields = [
            'id',
            'site_id',
            'code_site',
            'date',
            'statut_journee',
            'poids_organique_recu_kg',
            'biogaz_attendu_m3',
            'biogaz_mesure_m3',
            'ch4_pct',
            'temperature_c',
            'ph',
            'ecart_pct',
            'biogaz_cuisson_m3',
            'biogaz_perte_m3',
            'biogaz_valorise_m3',
            'electricite_kwh',
            'chaleur_kwh',
            'digestat_kg',
            'destination_digestat',
            'foyers_equivalents',
            'foyers_cuisson',
            'statuts_donnees',
        ]
        read_only_fields = [
            'id',
            'site_id',
            'code_site',
            'statuts_donnees',
        ]

    def get_statuts_donnees(self, obj):
        if obj.statuts_donnees:
            return obj.statuts_donnees
        return {
            "poids_organique_recu_kg": "mesure" if obj.poids_organique_recu_kg > 0 else "estime",
            "biogaz_attendu_m3": "estime",
            "biogaz_mesure_m3": "estime",
            "ch4_pct": "estime",
            "electricite_kwh": "estime",
            "chaleur_kwh": "estime",
            "digestat_kg": "estime",
            "foyers_equivalents": "estime",
        }


class ProductionGlobaleSerializer(serializers.Serializer):
    date = serializers.DateField()
    nb_sites = serializers.IntegerField()
    poids_organique_recu_kg = serializers.DecimalField(max_digits=12, decimal_places=2)
    biogaz_attendu_m3 = serializers.DecimalField(max_digits=12, decimal_places=2)
    biogaz_mesure_m3 = serializers.DecimalField(max_digits=12, decimal_places=2)
    electricite_kwh = serializers.DecimalField(max_digits=12, decimal_places=2)
    chaleur_kwh = serializers.DecimalField(max_digits=12, decimal_places=2)
    digestat_kg = serializers.DecimalField(max_digits=12, decimal_places=2)
    foyers_equivalents = serializers.DecimalField(max_digits=12, decimal_places=2)
    alertes_ouvertes = serializers.IntegerField()
    par_site = ProductionEnergieSerializer(many=True)


class MesureSiteSerializer(serializers.Serializer):
    date = serializers.DateField()
    biogaz_mesure_m3 = serializers.DecimalField(max_digits=9, decimal_places=2, min_value=Decimal('0'))
    ch4_pct = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal('0'), max_value=Decimal('100'))
    temperature_c = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    ph = serializers.DecimalField(max_digits=4, decimal_places=2, required=False, allow_null=True)
    source = serializers.ChoiceField(choices=['simule', 'capteur'])


class ClotureProductionSerializer(serializers.Serializer):
    destination_digestat = serializers.ChoiceField(choices=DestinationDigestat.choices)


class AlerteSerializer(serializers.ModelSerializer):
    site_id = serializers.UUIDField(source='site.id', read_only=True)
    code_site = serializers.CharField(source='site.code', read_only=True)
    resolue_par_id = serializers.UUIDField(source='resolue_par.id', read_only=True, allow_null=True)

    class Meta:
        model = Alerte
        fields = [
            'id',
            'site_id',
            'code_site',
            'type',
            'statut',
            'valeur_attendue',
            'valeur_mesuree',
            'ecart_pct',
            'description',
            'nb_occurrences',
            'date_creation',
            'date_derniere_occurrence',
            'date_resolution',
            'commentaire_resolution',
            'resolue_par_id',
        ]
        read_only_fields = fields


class ResoudreAlerteSerializer(serializers.Serializer):
    commentaire = serializers.CharField(required=True, allow_blank=False)
