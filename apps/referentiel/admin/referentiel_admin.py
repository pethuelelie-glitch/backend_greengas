from django.contrib import admin
from apps.referentiel.models import Site, Secteur, Bac


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ('code', 'nom', 'statut', 'capacite_kg_jour', 'latitude', 'longitude')
    list_filter = ('statut',)
    search_fields = ('code', 'nom')
    ordering = ('code',)


@admin.register(Secteur)
class SecteurAdmin(admin.ModelAdmin):
    list_display = ('code', 'nom', 'site', 'site_repli')
    search_fields = ('code', 'nom')
    ordering = ('code',)


@admin.register(Bac)
class BacAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'residence', 'secteur', 'statut',
        'capacite_kg', 'tare_kg', 'nb_foyers_declares', 'date_derniere_collecte'
    )
    list_filter = ('statut', 'secteur')
    search_fields = ('code', 'residence')
    ordering = ('code',)
