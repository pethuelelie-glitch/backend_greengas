from django.contrib import admin
from apps.energie.models import ProductionEnergie, Alerte


@admin.register(ProductionEnergie)
class ProductionEnergieAdmin(admin.ModelAdmin):
    list_display = (
        'site', 'date', 'statut_journee',
        'poids_organique_recu_kg', 'biogaz_attendu_m3', 'biogaz_mesure_m3',
        'ecart_pct', 'electricite_kwh', 'chaleur_kwh', 'digestat_kg', 'destination_digestat'
    )
    list_filter = ('statut_journee', 'site', 'destination_digestat')
    ordering = ('-date', 'site')


@admin.register(Alerte)
class AlerteAdmin(admin.ModelAdmin):
    list_display = (
        'site', 'type', 'statut', 'ecart_pct',
        'valeur_attendue', 'valeur_mesuree', 'nb_occurrences',
        'date_creation', 'date_resolution', 'resolue_par'
    )
    list_filter = ('statut', 'type', 'site')
    search_fields = ('site__nom', 'description', 'commentaire_resolution')
    ordering = ('-date_creation',)
    readonly_fields = ('id', 'date_creation', 'date_derniere_occurrence')
