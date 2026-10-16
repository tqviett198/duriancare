from rest_framework import serializers


class VoidSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)
