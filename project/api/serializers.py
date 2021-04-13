from rest_framework import serializers


class ModelDataSerializer(serializers.Serializer):
    initial_weights = serializers.JSONField()
    estimated_returns = serializers.JSONField()
    parameters = serializers.JSONField()
