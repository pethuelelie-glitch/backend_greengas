from rest_framework import serializers
from apps.supervision.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            'id',
            'type',
            'niveau',
            'titre',
            'message',
            'objet_type',
            'objet_id',
            'lue',
            'date_creation',
            'date_lecture',
        ]
        read_only_fields = fields
