from rest_framework import serializers
from apps.referentiel.models import Site, Secteur, Bac
from apps.comptes.models import Utilisateur, StatutValidation


class SiteSerializer(serializers.ModelSerializer):
    alertes_ouvertes = serializers.SerializerMethodField()

    class Meta:
        model = Site
        fields = [
            'id', 'code', 'nom', 'statut', 'capacite_kg_jour',
            'latitude', 'longitude', 'alertes_ouvertes'
        ]
        read_only_fields = ['id', 'alertes_ouvertes']

    def get_alertes_ouvertes(self, obj):
        from apps.energie.models import Alerte, StatutAlerte
        return Alerte.objects.filter(site=obj, statut=StatutAlerte.OUVERTE).count()


class SecteurSerializer(serializers.ModelSerializer):
    site_code = serializers.CharField(source='site.code', read_only=True)
    site_repli_code = serializers.CharField(source='site_repli.code', read_only=True)

    class Meta:
        model = Secteur
        fields = [
            'id', 'code', 'nom', 'site', 'site_code',
            'site_repli', 'site_repli_code'
        ]
        read_only_fields = ['id']


class BacSerializer(serializers.ModelSerializer):
    secteur = serializers.PrimaryKeyRelatedField(queryset=Secteur.objects.all(), required=False)
    secteur_id = serializers.PrimaryKeyRelatedField(
        queryset=Secteur.objects.all(),
        source='secteur',
        write_only=True,
        required=False
    )
    secteur_code = serializers.CharField(source='secteur.code', read_only=True)
    nb_citoyens_valides = serializers.SerializerMethodField()
    scans_valides_periode = serializers.SerializerMethodField()

    class Meta:
        model = Bac
        fields = [
            'id', 'code', 'residence', 'secteur', 'secteur_id', 'secteur_code',
            'nb_foyers_declares', 'latitude', 'longitude',
            'tare_kg', 'capacite_kg', 'statut',
            'nb_citoyens_valides', 'scans_valides_periode',
            'date_derniere_collecte'
        ]
        read_only_fields = ['id', 'date_derniere_collecte']

    def validate(self, attrs):
        if self.instance is None and 'secteur' not in attrs:
            raise serializers.ValidationError({"secteur_id": "Le secteur est obligatoire."})
        return attrs


    def get_nb_citoyens_valides(self, obj):
        return Utilisateur.objects.filter(bac=obj, statut_validation=StatutValidation.VALIDE).count()

    def get_scans_valides_periode(self, obj):
        from apps.collecte.models import Scan
        queryset = Scan.objects.filter(bac=obj, compte=True)
        if obj.date_derniere_collecte:
            queryset = queryset.filter(horodatage__gt=obj.date_derniere_collecte)
        return queryset.count()
