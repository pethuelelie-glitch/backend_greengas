from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from apps.referentiel.models import Site, Secteur, Bac
from apps.referentiel.serializers import SiteSerializer, SecteurSerializer, BacSerializer
from apps.comptes.permissions import EstAdmin, EstAdminOuResponsable


class SiteListView(generics.ListAPIView):
    """GET /api/v1/sites/ — Liste des sites méthaniseurs (non paginée)"""
    queryset = Site.objects.all().order_by('code')
    serializer_class = SiteSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class SiteDetailUpdateView(generics.RetrieveUpdateAPIView):
    """
    GET /api/v1/sites/{id}/
    PATCH /api/v1/sites/{id}/ — Changer le statut (nominal/alerte/maintenance)
    """
    queryset = Site.objects.all()
    serializer_class = SiteSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'

    def get_permissions(self):
        if self.request.method in ['PATCH', 'PUT']:
            return [EstAdminOuResponsable()]
        return [IsAuthenticated()]

    def perform_update(self, serializer):
        ancien_statut = self.get_object().statut
        site = serializer.save()
        nouveau_statut = site.statut

        if ancien_statut != nouveau_statut:
            try:
                from apps.comptes.models import Role, Utilisateur
                from apps.supervision.models import TypeNotification, NiveauNotification
                from apps.supervision.services import notifier_utilisateurs
                dest = Utilisateur.objects.filter(role__in=[Role.RESPONSABLE_METHANISATION, Role.ADMINISTRATEUR], actif=True)
                secteur = site.secteurs.first()
                repli = secteur.site_repli if secteur else None
                if nouveau_statut == 'maintenance':
                    if secteur and repli:
                        msg = f"{site.code} en maintenance : les tournées {secteur.code} partent vers {repli.code}."
                    else:
                        msg = f"{site.code} est passé en maintenance."
                else:
                    msg = f"{site.code} remis en service ({nouveau_statut})."

                notifier_utilisateurs(
                    destinataires=dest,
                    type=TypeNotification.SITE_MAINTENANCE,
                    niveau=NiveauNotification.ATTENTION,
                    titre="Maintenance site",
                    message=msg,
                    objet_type="site",
                    objet_id=site.id,
                    auteur=self.request.user
                )
            except Exception:
                pass


class SecteurListView(generics.ListAPIView):
    """GET /api/v1/secteurs/ — Liste des secteurs (non paginée)"""
    queryset = Secteur.objects.all().order_by('code')
    serializer_class = SecteurSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None



class SecteurDetailUpdateView(generics.RetrieveUpdateAPIView):
    """
    GET /api/v1/secteurs/{id}/
    PATCH /api/v1/secteurs/{id}/ — Modifier les sites rattachés (Admin)
    """
    queryset = Secteur.objects.all()
    serializer_class = SecteurSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'

    def get_permissions(self):
        if self.request.method in ['PATCH', 'PUT']:
            return [EstAdmin()]
        return [IsAuthenticated()]


class BacListCreateView(generics.ListCreateAPIView):
    """
    GET /api/v1/bacs/ — Liste des bacs (filtrable par secteur et statut)
    POST /api/v1/bacs/ — Création d'un bac (Admin)
    """
    serializer_class = BacSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Bac.objects.all().order_by('code')
        secteur = self.request.query_params.get('secteur')
        if secteur:
            queryset = queryset.filter(secteur__code=secteur)
        statut = self.request.query_params.get('statut')
        if statut:
            queryset = queryset.filter(statut=statut)
        return queryset

    def get_permissions(self):
        if self.request.method == 'POST':
            return [EstAdmin()]
        return [IsAuthenticated()]


class BacDetailUpdateView(generics.RetrieveUpdateAPIView):
    """
    GET /api/v1/bacs/{id}/ — Détail d'un bac
    PATCH /api/v1/bacs/{id}/ — Modification d'un bac (Admin)
    """
    queryset = Bac.objects.all()
    serializer_class = BacSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'

    def get_permissions(self):
        if self.request.method in ['PATCH', 'PUT']:
            return [EstAdmin()]
        return [IsAuthenticated()]
