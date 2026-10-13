from django.contrib import admin
from apps.tri.models import LotTrie


@admin.register(LotTrie)
class LotTrieAdmin(admin.ModelAdmin):
    list_display = ('code_lot', 'tournee', 'categorie', 'poids_kg', 'part_pct', 'destination', 'site')
    list_filter = ('categorie', 'destination')
    search_fields = ('code_lot', 'tournee__code')
    ordering = ('-tournee__date', 'code_lot')
