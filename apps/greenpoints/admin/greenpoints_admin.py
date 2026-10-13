from django.contrib import admin
from apps.greenpoints.models import GreenPointsTransaction, Recompense, Echange


@admin.register(GreenPointsTransaction)
class GreenPointsTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'citoyen', 'points', 'statut', 'poids_attribue_kg',
        'valeur_kg', 'coef_qualite', 'scans_citoyen', 'scans_bac', 'date'
    )
    list_filter = ('statut',)
    search_fields = ('citoyen__nom', 'citoyen__telephone', 'tournee__code')
    ordering = ('-date',)
    readonly_fields = ('id', 'date')


@admin.register(Recompense)
class RecompenseAdmin(admin.ModelAdmin):
    list_display = ('nom', 'cout_points', 'partenaire', 'actif')
    list_filter = ('actif',)
    search_fields = ('nom', 'partenaire')
    ordering = ('cout_points',)


@admin.register(Echange)
class EchangeAdmin(admin.ModelAdmin):
    list_display = ('citoyen', 'recompense', 'cout_points', 'date')
    search_fields = ('citoyen__nom', 'citoyen__telephone', 'recompense__nom')
    ordering = ('-date',)
    readonly_fields = ('id', 'date')
