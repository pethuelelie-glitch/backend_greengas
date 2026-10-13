from django.contrib import admin
from apps.collecte.models import Scan, Tournee, Collecte


@admin.register(Scan)
class ScanAdmin(admin.ModelAdmin):
    list_display = ('citoyen', 'bac', 'statut', 'distance_m', 'compte', 'horodatage')
    list_filter = ('statut', 'compte')
    search_fields = ('citoyen__nom', 'citoyen__telephone', 'bac__code')
    ordering = ('-horodatage',)
    readonly_fields = ('id', 'horodatage')


@admin.register(Tournee)
class TourneeAdmin(admin.ModelAdmin):
    list_display = ('code', 'date', 'secteur', 'site', 'collecteur', 'statut', 'niveau_contamination')
    list_filter = ('statut', 'secteur', 'niveau_contamination')
    search_fields = ('code', 'collecteur__nom')
    ordering = ('-date', 'code')
    filter_horizontal = ('bacs',)


@admin.register(Collecte)
class CollecteAdmin(admin.ModelAdmin):
    list_display = (
        'bac', 'tournee', 'collecteur', 'statut',
        'poids_brut_kg', 'tare_kg', 'poids_net_kg', 'scans_valides',
        'kg_par_scan', 'statut_controle'
    )
    list_filter = ('statut', 'statut_controle', 'source')
    search_fields = ('bac__code', 'tournee__code', 'collecteur__nom')
    ordering = ('-date_ouverture',)
