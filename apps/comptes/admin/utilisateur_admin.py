from django.contrib import admin
from apps.comptes.models import Utilisateur


@admin.register(Utilisateur)
class UtilisateurAdmin(admin.ModelAdmin):
    list_display = (
        'nom', 'telephone', 'role', 'statut_validation',
        'telephone_verifie', 'bac', 'actif', 'date_creation'
    )
    list_filter = ('role', 'statut_validation', 'telephone_verifie', 'actif')
    search_fields = ('nom', 'telephone', 'email')
    ordering = ('-date_creation',)
    readonly_fields = ('id', 'date_creation')
    fieldsets = (
        ('Informations Générales', {
            'fields': ('id', 'nom', 'telephone', 'email', 'role', 'actif', 'is_staff', 'is_superuser')
        }),
        ('Profil Citoyen / Référent', {
            'fields': ('bac', 'telephone_verifie', 'statut_validation', 'date_inscription')
        }),
        ('Dates', {
            'fields': ('date_creation', 'last_login')
        }),
    )
