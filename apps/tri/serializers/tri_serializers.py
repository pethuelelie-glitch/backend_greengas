from decimal import Decimal
from rest_framework import serializers

from apps.tri.models.lot_trie import LotTrie, Categorie, Destination
from apps.collecte.models.tournee import NiveauContamination


class LotTrieSerializer(serializers.ModelSerializer):
    """Sérialiseur d'un lot trié issu d'une tournée"""
    tournee_id = serializers.UUIDField(source='tournee.id', read_only=True)
    site_id = serializers.UUIDField(source='site.id', read_only=True, allow_null=True)

    class Meta:
        model = LotTrie
        fields = [
            'id', 'code_lot', 'tournee_id', 'categorie',
            'poids_kg', 'part_pct', 'destination', 'site_id'
        ]
        read_only_fields = ['id', 'code_lot', 'tournee_id', 'part_pct', 'destination', 'site_id']


class LotRequeteItemSerializer(serializers.Serializer):
    """Élément de lot dans la requête de validation de tri"""
    categorie = serializers.ChoiceField(choices=Categorie.choices)
    poids_kg = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=Decimal('0.00'))


class TriRequeteSerializer(serializers.Serializer):
    """Payload de saisie et validation du tri d'une tournée par l'opérateur"""
    niveau_contamination = serializers.ChoiceField(choices=NiveauContamination.choices)
    lots = LotRequeteItemSerializer(many=True)
    motif_ecart = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)

    def validate_lots(self, lots):
        if not lots:
            raise serializers.ValidationError("Au moins un lot doit être renseigné.")
        categories = [item['categorie'] for item in lots]
        if len(categories) != len(set(categories)):
            raise serializers.ValidationError("Une seule entrée par catégorie de matière est autorisée.")
        return lots


class ResultatTriSerializer(serializers.Serializer):
    """Résultat consolidé du tri d'une tournée avec ses lots et distributions de GreenPoints"""
    tournee_id = serializers.UUIDField()
    code_tournee = serializers.CharField()
    niveau_contamination = serializers.CharField()
    coef_qualite = serializers.DecimalField(max_digits=4, decimal_places=2)
    poids_collecte_kg = serializers.DecimalField(max_digits=8, decimal_places=2)
    poids_trie_kg = serializers.DecimalField(max_digits=8, decimal_places=2)
    ecart_pct = serializers.DecimalField(max_digits=6, decimal_places=2)
    motif_ecart = serializers.CharField(allow_null=True)
    valeur_kg = serializers.DecimalField(max_digits=6, decimal_places=4)
    lots = LotTrieSerializer(many=True)
    nb_transactions = serializers.IntegerField()
    points_credites = serializers.IntegerField()
    points_en_attente = serializers.IntegerField()
    production_id = serializers.UUIDField(allow_null=True)
    date_validation = serializers.DateTimeField()
    valide_par_id = serializers.UUIDField()
