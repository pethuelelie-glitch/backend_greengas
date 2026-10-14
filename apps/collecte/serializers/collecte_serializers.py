from decimal import Decimal
from django.db.models import Sum
from rest_framework import serializers

from apps.collecte.models import (
    Scan, StatutScan,
    Tournee, StatutTournee, MotifAffectation, NiveauContamination,
    Collecte, StatutCollecte, StatutControle, SourceMesure
)
from apps.comptes.models import Utilisateur, Role
from apps.referentiel.models import Secteur, Site, Bac
from apps.referentiel.serializers import BacSerializer


class ScanSerializer(serializers.ModelSerializer):
    """Sérialiseur complet d'un scan de bac par un citoyen"""
    citoyen_nom = serializers.CharField(source='citoyen.nom', read_only=True)
    citoyen_telephone = serializers.CharField(source='citoyen.telephone', read_only=True)
    code_bac = serializers.CharField(source='bac.code', read_only=True)
    bac_code = serializers.CharField(source='bac.code', read_only=True)

    class Meta:
        model = Scan
        fields = [
            'id', 'citoyen', 'citoyen_nom', 'citoyen_telephone',
            'bac', 'code_bac', 'bac_code',
            'horodatage', 'latitude', 'longitude',
            'distance_m', 'statut', 'compte'
        ]
        read_only_fields = [
            'id', 'citoyen', 'horodatage', 'distance_m', 'statut', 'compte'
        ]


class ScanRequeteSerializer(serializers.Serializer):
    """Payload de requête pour scanner un bac"""
    code_bac = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    bac_id = serializers.UUIDField(required=False, allow_null=True)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)

    def validate(self, attrs):
        code_bac = attrs.get('code_bac')
        bac_id = attrs.get('bac_id')
        request = self.context.get('request')
        user = getattr(request, 'user', None)

        if not code_bac and not bac_id:
            if not (user and getattr(user, 'bac', None)):
                raise serializers.ValidationError("Le paramètre 'code_bac' ou 'bac_id' est obligatoire.")
        return attrs


class CollecteSerializer(serializers.ModelSerializer):
    """Sérialiseur de collecte d'un bac lors d'une tournée"""
    tournee_code = serializers.CharField(source='tournee.code', read_only=True)
    code_bac = serializers.CharField(source='bac.code', read_only=True)
    bac_residence = serializers.CharField(source='bac.residence', read_only=True)
    collecteur_nom = serializers.CharField(source='collecteur.nom', read_only=True)

    class Meta:
        model = Collecte
        fields = [
            'id', 'tournee', 'tournee_code',
            'bac', 'code_bac', 'bac_residence',
            'collecteur', 'collecteur_nom',
            'statut', 'poids_brut_kg', 'tare_kg', 'poids_net_kg', 'source',
            'scans_valides', 'kg_par_scan', 'statut_controle',
            'date_ouverture', 'date_pesee', 'date_validation'
        ]
        read_only_fields = [
            'id', 'tournee', 'bac', 'collecteur', 'statut',
            'tare_kg', 'poids_net_kg', 'scans_valides', 'kg_par_scan',
            'statut_controle', 'date_ouverture', 'date_pesee', 'date_validation'
        ]


class TourneeSerializer(serializers.ModelSerializer):
    """Sérialiseur résumé pour la liste des tournées"""
    secteur_code = serializers.CharField(source='secteur.code', read_only=True)
    secteur_nom = serializers.CharField(source='secteur.nom', read_only=True)
    code_site = serializers.CharField(source='site.code', read_only=True)
    site_nom = serializers.CharField(source='site.nom', read_only=True)
    collecteur_nom = serializers.CharField(source='collecteur.nom', read_only=True)
    collecteur_telephone = serializers.CharField(source='collecteur.telephone', read_only=True)

    nb_bacs = serializers.SerializerMethodField()
    nb_bacs_collectes = serializers.SerializerMethodField()
    poids_collecte_kg = serializers.SerializerMethodField()

    class Meta:
        model = Tournee
        fields = [
            'id', 'code', 'date',
            'secteur', 'secteur_code', 'secteur_nom',
            'site', 'code_site', 'site_nom',
            'motif_affectation',
            'collecteur', 'collecteur_nom', 'collecteur_telephone',
            'statut', 'niveau_contamination',
            'nb_bacs', 'nb_bacs_collectes', 'poids_collecte_kg'
        ]
        read_only_fields = [
            'id', 'code', 'site', 'motif_affectation', 'statut',
            'nb_bacs', 'nb_bacs_collectes', 'poids_collecte_kg'
        ]

    def get_nb_bacs(self, obj):
        return obj.bacs.count()

    def get_nb_bacs_collectes(self, obj):
        return obj.collectes.filter(statut=StatutCollecte.VALIDEE).count()

    def get_poids_collecte_kg(self, obj):
        total = obj.collectes.filter(poids_net_kg__isnull=False).aggregate(total=Sum('poids_net_kg'))['total']
        return float(total) if total is not None else 0.0


class TourneeDetailSerializer(TourneeSerializer):
    """Sérialiseur détaillé d'une tournée avec ses bacs et ses collectes"""
    bacs = BacSerializer(many=True, read_only=True)
    collectes = CollecteSerializer(many=True, read_only=True)

    class Meta(TourneeSerializer.Meta):
        fields = TourneeSerializer.Meta.fields + ['bacs', 'collectes']


class TourneeCreationSerializer(serializers.Serializer):
    """Payload pour la création d'une tournée par l'administrateur"""
    secteur = serializers.PrimaryKeyRelatedField(queryset=Secteur.objects.all(), required=False)
    secteur_id = serializers.PrimaryKeyRelatedField(queryset=Secteur.objects.all(), source='secteur', required=False)
    date = serializers.DateField()
    collecteur = serializers.PrimaryKeyRelatedField(queryset=Utilisateur.objects.all(), required=False)
    collecteur_id = serializers.PrimaryKeyRelatedField(queryset=Utilisateur.objects.all(), source='collecteur', required=False)
    bacs = serializers.PrimaryKeyRelatedField(queryset=Bac.objects.all(), many=True, required=False)
    bac_ids = serializers.PrimaryKeyRelatedField(queryset=Bac.objects.all(), many=True, source='bacs', required=False)

    def validate(self, attrs):
        if 'secteur' not in attrs:
            raise serializers.ValidationError({"secteur_id": "Ce champ est obligatoire."})
        if 'collecteur' not in attrs:
            raise serializers.ValidationError({"collecteur_id": "Ce champ est obligatoire."})
        if attrs['collecteur'].role != Role.COLLECTEUR:
            raise serializers.ValidationError({"collecteur_id": "L'utilisateur assigné doit avoir le rôle de collecteur."})
        return attrs



class PeseeRequeteSerializer(serializers.Serializer):
    """Payload de pesée pour une collecte"""
    poids_brut_kg = serializers.DecimalField(max_digits=7, decimal_places=2, min_value=Decimal('0.00'))
    source = serializers.ChoiceField(
        choices=SourceMesure.choices,
        default=SourceMesure.CAPTEUR,
        required=False
    )
