from rest_framework import serializers
from apps.supervision.models import Parametre, JournalAudit


class ParametreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Parametre
        fields = [
            'cle',
            'valeur',
            'unite',
            'statut',
            'description',
            'source',
            'date_modification',
        ]
        read_only_fields = [
            'cle',
            'unite',
            'statut',
            'description',
            'source',
            'date_modification',
        ]


class ParametreUpdateSerializer(serializers.Serializer):
    valeur = serializers.DecimalField(
        max_digits=12,
        decimal_places=4,
        required=True
    )
    motif = serializers.CharField(
        required=False,
        allow_blank=True,
        default="Modification du paramètre système par l'administrateur"
    )


class EntreeJournalSerializer(serializers.ModelSerializer):
    auteur_id = serializers.UUIDField(source='auteur.id', read_only=True)
    nom_auteur = serializers.CharField(source='auteur.nom', read_only=True)

    class Meta:
        model = JournalAudit
        fields = [
            'id',
            'date',
            'auteur_id',
            'nom_auteur',
            'action',
            'objet_type',
            'objet_id',
            'ancienne_valeur',
            'nouvelle_valeur',
            'motif',
        ]
        read_only_fields = fields


class ElementVerificationSerializer(serializers.Serializer):
    type = serializers.CharField()
    objet_type = serializers.CharField()
    objet_id = serializers.CharField()
    libelle = serializers.CharField()
    details = serializers.DictField()
    date = serializers.DateTimeField()


class CitoyenTracabiliteSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    nom = serializers.CharField()
    statut_validation = serializers.CharField()


class EtapeTracabiliteSerializer(serializers.Serializer):
    collecte = serializers.DictField()
    tournee = serializers.DictField()
    lots = serializers.ListField(child=serializers.DictField())
    valeur_kg = serializers.FloatField(allow_null=True)
    coef_qualite = serializers.FloatField(allow_null=True)
    points_bac = serializers.FloatField(allow_null=True)
    transactions = serializers.ListField(child=serializers.DictField())
    production = serializers.DictField(allow_null=True)


class TracabiliteBacSerializer(serializers.Serializer):
    bac = serializers.DictField()
    citoyens = CitoyenTracabiliteSerializer(many=True)
    historique = EtapeTracabiliteSerializer(many=True)

