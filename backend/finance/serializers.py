from rest_framework import serializers

from common.permissions import FarmScopedField
from farms.models import Plot, Season

from .models import LedgerEntry


class LedgerEntrySerializer(serializers.ModelSerializer):
    plot = FarmScopedField(queryset=Plot.objects.all(), farm_lookup="farm_id", required=False, allow_null=True)
    season = FarmScopedField(queryset=Season.objects.all(), farm_lookup="farm_id", required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=14, decimal_places=0, min_value=1)
    is_generated = serializers.SerializerMethodField()

    class Meta:
        model = LedgerEntry
        fields = ["id", "plot", "season", "type", "category", "amount", "txn_date", "description",
                  "source_log", "is_generated", "status", "void_reason", "created_at"]
        read_only_fields = ["id", "source_log", "status", "void_reason", "created_at"]

    def get_is_generated(self, obj) -> bool:
        return obj.source_log_id is not None
