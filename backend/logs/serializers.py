from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from catalog.models import InputProduct
from common.permissions import FarmScopedField
from farms.models import FarmMembership, Plot, Season

from .models import FarmLog, FarmLogInput

User = get_user_model()


class FarmLogInputSerializer(serializers.ModelSerializer):
    product = FarmScopedField(queryset=InputProduct.objects.filter(is_active=True),
                              farm_lookup="farm_id", allow_global=True)
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    unit_cost = serializers.DecimalField(max_digits=14, decimal_places=0, min_value=0)

    class Meta:
        model = FarmLogInput
        fields = ["id", "product", "quantity", "unit_cost", "total_cost", "warning_acknowledged"]
        read_only_fields = ["id", "total_cost", "warning_acknowledged"]


class FarmLogSerializer(serializers.ModelSerializer):
    plot = FarmScopedField(queryset=Plot.objects.all(), farm_lookup="farm_id")
    season = FarmScopedField(queryset=Season.objects.all(), farm_lookup="farm_id",
                             required=False, allow_null=True)
    performed_by = FarmScopedField(queryset=User.objects.all(), farm_lookup="memberships__farm_id",
                                   required=False, allow_null=True)
    inputs = FarmLogInputSerializer(many=True, required=False)
    acknowledged_warnings = serializers.ListField(child=serializers.IntegerField(), write_only=True,
                                                  required=False)
    generated_expense = serializers.SerializerMethodField()
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = FarmLog
        fields = ["id", "plot", "season", "activity_type", "activity_date", "description",
                  "performed_by", "created_by", "status", "void_reason", "inputs",
                  "acknowledged_warnings", "generated_expense", "created_at"]
        read_only_fields = ["id", "status", "void_reason", "created_at"]

    def validate_activity_date(self, value):
        if value > timezone.localdate():     # BR-04: kế hoạch tương lai đi qua Công việc
            raise serializers.ValidationError("Ngày thực hiện không được ở tương lai.")
        return value

    def get_generated_expense(self, log):
        entries = list(log.expenses.filter(status="ACTIVE"))
        if not entries:
            return None
        if len(entries) == 1:
            e = entries[0]
            return {"id": e.id, "amount": str(e.amount), "category": e.category}
        total_amount = sum((e.amount for e in entries), Decimal("0"))
        return {
            "id": entries[0].id,
            "amount": str(total_amount),
            "category": "MIXED",
            "items": [{"id": e.id, "amount": str(e.amount), "category": e.category} for e in entries],
        }
