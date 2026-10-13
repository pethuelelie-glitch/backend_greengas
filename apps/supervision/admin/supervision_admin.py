from django.contrib import admin
from apps.supervision.models import Parametre, JournalAudit


@admin.register(Parametre)
class ParametreAdmin(admin.ModelAdmin):
    list_display = ('cle', 'valeur', 'unite', 'statut', 'description', 'date_modification')
    list_filter = ('statut',)
    search_fields = ('cle', 'description', 'source')
    ordering = ('cle',)


@admin.register(JournalAudit)
class JournalAuditAdmin(admin.ModelAdmin):
    list_display = ('date', 'auteur', 'action', 'objet_type', 'objet_id', 'motif')
    list_filter = ('objet_type', 'action')
    search_fields = ('auteur__nom', 'action', 'objet_id', 'motif')
    ordering = ('-date',)
    readonly_fields = ('id', 'date', 'auteur', 'action', 'objet_type', 'objet_id', 'ancienne_valeur', 'nouvelle_valeur', 'motif')
