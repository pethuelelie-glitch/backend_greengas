from rest_framework import serializers

from apps.greenpoints.models import GreenPointsTransaction, Recompense, Echange


class GreenPointsTransactionSerializer(serializers.ModelSerializer):
    """Sérialiseur d'une transaction de distribution de GreenPoints"""
    citoyen_id = serializers.UUIDField(source='citoyen.id', read_only=True)
    bac_id = serializers.UUIDField(source='bac.id', read_only=True)
    tournee_id = serializers.UUIDField(source='tournee.id', read_only=True)
    collecte_id = serializers.UUIDField(source='collecte.id', read_only=True)
    code_tournee = serializers.CharField(source='tournee.code', read_only=True)

    class Meta:
        model = GreenPointsTransaction
        fields = [
            'id', 'citoyen_id', 'bac_id', 'tournee_id', 'collecte_id',
            'code_tournee', 'scans_citoyen', 'scans_bac',
            'poids_attribue_kg', 'valeur_kg', 'coef_qualite',
            'points', 'statut', 'date'
        ]
        read_only_fields = fields


class SoldeSerializer(serializers.Serializer):
    """Solde de GreenPoints d'un citoyen"""
    citoyen_id = serializers.UUIDField()
    solde = serializers.IntegerField()
    points_en_attente = serializers.IntegerField()
    total_gagne = serializers.IntegerField()
    total_echange = serializers.IntegerField()


class RecompenseSerializer(serializers.ModelSerializer):
    """Sérialiseur complet d'une récompense disponible au catalogue"""

    class Meta:
        model = Recompense
        fields = ['id', 'nom', 'description', 'cout_points', 'partenaire', 'actif']
        read_only_fields = ['id']


class RecompenseEcritureSerializer(serializers.ModelSerializer):
    """Payload d'écriture ou modification d'une récompense par l'administrateur"""
    nom = serializers.CharField(required=False)
    description = serializers.CharField(required=False)
    cout_points = serializers.IntegerField(required=False, min_value=1)
    partenaire = serializers.CharField(required=False)
    actif = serializers.BooleanField(required=False, default=True)

    class Meta:
        model = Recompense
        fields = ['nom', 'description', 'cout_points', 'partenaire', 'actif']

    def validate(self, attrs):
        if self.instance is None:
            # Création (POST) : tous les champs obligatoires doivent être présents
            required_fields = ['nom', 'description', 'cout_points', 'partenaire']
            missing = [f for f in required_fields if f not in attrs]
            if missing:
                raise serializers.ValidationError({f: ["Ce champ est obligatoire."] for f in missing})
        return attrs


class EchangeSerializer(serializers.ModelSerializer):
    """Sérialiseur complet d'un échange de GreenPoints contre une récompense"""
    citoyen_id = serializers.UUIDField(source='citoyen.id', read_only=True)
    recompense_id = serializers.UUIDField(source='recompense.id', read_only=True)
    nom_recompense = serializers.CharField(source='recompense.nom', read_only=True)

    class Meta:
        model = Echange
        fields = ['id', 'citoyen_id', 'recompense_id', 'nom_recompense', 'cout_points', 'date']
        read_only_fields = fields


class EchangeCreationSerializer(serializers.Serializer):
    """Payload pour initier un échange de points par un citoyen"""
    recompense_id = serializers.UUIDField(required=True)
