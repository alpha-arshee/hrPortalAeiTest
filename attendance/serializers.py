from django.core import serializers
from .models import AttendanceRequest


class AttendanceRequestSerializer(serializers.ModelSerializer):
    latitude = serializers.FloatField(required=False, write_only=False)
    longitude = serializers.FloatField(required=False, write_only=False)
    location_accuracy = serializers.FloatField(required=False)

    class Meta:
        model = AttendanceRequest
        fields = [
            'id', 'user', 'request_date', 'reason', 'punch_time', 'status',
            'submitted_at', 'latitude', 'longitude', 'location_accuracy',
            'location_captured', 'reviewed_by', 'reviewed_at', 'rejection_reason',
        ]
        read_only_fields = ['id', 'user', 'status', 'submitted_at', 'reviewed_by',
                             'reviewed_at', 'rejection_reason']

    def create(self, validated_data):
        lat = validated_data.get('latitude')
        lng = validated_data.get('longitude')
        validated_data['location_captured'] = lat is not None and lng is not None
        validated_data['user'] = self.context['request'].user
        return AttendanceRequest.objects.create(**validated_data)