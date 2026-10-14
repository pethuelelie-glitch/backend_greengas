from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import NotFound
from django.utils import timezone

from apps.supervision.models import Notification
from apps.supervision.serializers import NotificationSerializer
from apps.comptes.models import Role


class NotificationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'taille_page'
    max_page_size = 100

    def get_page_size(self, request):
        if 'page_size' in request.query_params and 'taille_page' not in request.query_params:
            try:
                return int(request.query_params['page_size'])
            except (ValueError, TypeError):
                pass
        return super().get_page_size(request)


class NotificationListView(generics.ListAPIView):
    """
    GET /api/v1/notifications/
    Liste paginée des notifications de l'utilisateur connecté (de la plus récente à la plus ancienne).
    Filtres : lue (true/false), type, page, taille_page.
    Le compte technique capteur reçoit une liste vide.
    """
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = NotificationPagination

    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'role', None) == Role.CAPTEUR:
            return Notification.objects.none()

        queryset = Notification.objects.filter(destinataire=user).order_by('-date_creation')

        lue_param = self.request.query_params.get('lue')
        if lue_param is not None:
            if lue_param.lower() in ['true', '1']:
                queryset = queryset.filter(lue=True)
            elif lue_param.lower() in ['false', '0']:
                queryset = queryset.filter(lue=False)

        type_param = self.request.query_params.get('type')
        if type_param:
            queryset = queryset.filter(type=type_param)

        return queryset


class NotificationCompteurView(APIView):
    """
    GET /api/v1/notifications/compteur/
    Renvoie le nombre de notifications non-lues de l'utilisateur connecté.
    Exemple : {"non_lues": 3}
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if getattr(user, 'role', None) == Role.CAPTEUR:
            return Response({"non_lues": 0}, status=status.HTTP_200_OK)

        non_lues = Notification.objects.filter(destinataire=user, lue=False).count()
        return Response({"non_lues": non_lues}, status=status.HTTP_200_OK)


class NotificationMarquerLueView(APIView):
    """
    POST /api/v1/notifications/{id}/lue/
    Marque une notification comme lue (lue = true, date_lecture renseignée).
    Renvoie 404 INTROUVABLE si la notification n'existe pas ou appartient à un autre utilisateur.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, id):
        user = request.user
        try:
            notif = Notification.objects.get(id=id, destinataire=user)
        except Notification.DoesNotExist:
            raise NotFound(detail="Notification introuvable.", code="INTROUVABLE")

        if not notif.lue:
            notif.lue = True
            notif.date_lecture = timezone.now()
            notif.save(update_fields=['lue', 'date_lecture'])

        serializer = NotificationSerializer(notif)
        return Response(serializer.data, status=status.HTTP_200_OK)


class NotificationToutLireView(APIView):
    """
    POST /api/v1/notifications/tout-lire/
    Marque toutes les notifications non-lues de l'utilisateur connecté comme lues.
    Renvoie {"marquees": N}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if getattr(user, 'role', None) == Role.CAPTEUR:
            return Response({"marquees": 0}, status=status.HTTP_200_OK)

        count = Notification.objects.filter(destinataire=user, lue=False).update(
            lue=True,
            date_lecture=timezone.now()
        )
        return Response({"marquees": count}, status=status.HTTP_200_OK)
