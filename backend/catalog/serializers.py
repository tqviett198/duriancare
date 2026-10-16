from rest_framework import serializers

from .models import InputProduct, Variety


class VarietySerializer(serializers.ModelSerializer):
    class Meta:
        model = Variety
        fields = ["id", "name", "description"]


class InputProductSerializer(serializers.ModelSerializer):
    is_global = serializers.SerializerMethodField()

    class Meta:
        model = InputProduct
        fields = ["id", "name", "kind", "active_ingredient", "unit", "phi_days",
                  "max_applications_per_season", "registered_for_durian",
                  "source_note", "source_url", "verified_at", "is_demo", "is_active", "is_global"]
        read_only_fields = ["id", "is_demo", "registered_for_durian", "source_note", "source_url", "verified_at"]

    def get_is_global(self, obj) -> bool:
        return obj.farm_id is None

    def validate(self, attrs):
        kind = attrs.get("kind", getattr(self.instance, "kind", None))
        phi = attrs.get("phi_days", getattr(self.instance, "phi_days", None))
        if kind == InputProduct.Kind.PESTICIDE and phi is None:
            raise serializers.ValidationError({"phi_days": ["Thuốc BVTV bắt buộc có số ngày cách ly (theo nhãn)."]})
        if self.instance is None:
            attrs["registered_for_durian"] = InputProduct.DurianStatus.UNKNOWN
        return attrs
