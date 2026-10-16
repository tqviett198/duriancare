from decimal import Decimal

from rest_framework import serializers

from common.permissions import FarmScopedField
from farms.models import Plot, Season
from .models import BatchGrade, BatchStock, HarvestBatch, LabTest


class BatchStockInputSerializer(serializers.Serializer):
    """Dữ liệu phân loại khi tạo lô (write-only)."""
    grade = serializers.ChoiceField(choices=BatchGrade.choices)
    qty_kg = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    estimated_price_per_kg = serializers.DecimalField(
        max_digits=10, decimal_places=0, min_value=Decimal("0"), required=False, allow_null=True
    )


class BatchStockSerializer(serializers.ModelSerializer):
    grade_display = serializers.CharField(source="get_grade_display", read_only=True)

    class Meta:
        model = BatchStock
        fields = ["id", "grade", "grade_display", "qty_kg", "remaining_kg",
                  "estimated_price_per_kg"]


class HarvestBatchSerializer(serializers.ModelSerializer):
    """Serializer đọc chi tiết một lô thu hoạch."""
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    stocks = BatchStockSerializer(many=True, read_only=True)
    lab_tests = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = HarvestBatch
        fields = [
            "id", "farm", "plot", "season", "batch_code", "harvest_date",
            "phi_safe_date", "total_kg", "remaining_kg", "status", "status_display",
            "note", "override_reason", "stocks", "lab_tests",
            "created_by", "created_at", "updated_at",
        ]
        read_only_fields = fields


class HarvestBatchCreateSerializer(serializers.Serializer):
    """Tạo mới lô thu hoạch – validate input trước khi gọi service."""
    plot = FarmScopedField(queryset=Plot.objects.all())
    season = FarmScopedField(queryset=Season.objects.all(), required=False, allow_null=True)
    batch_code = serializers.CharField(max_length=50)
    harvest_date = serializers.DateField()
    stocks = BatchStockInputSerializer(many=True, min_length=1)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    override_reason = serializers.CharField(
        required=False, allow_blank=True, default="",
        help_text="BR-08: Lý do OWNER cho phép thu hoạch dù chưa hết PHI.",
    )

    def validate_stocks(self, value):
        grades = [s["grade"] for s in value]
        if len(grades) != len(set(grades)):
            raise serializers.ValidationError("Không được có hai dòng cùng phân loại (grade) trong một lô.")
        return value


class VoidBatchSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, allow_blank=False)


class LabTestSerializer(serializers.ModelSerializer):
    """Serializer đọc kết quả kiểm nghiệm."""
    result_display = serializers.CharField(source="get_result_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = LabTest
        fields = [
            "id", "batch", "tested_date", "lab_name", "result", "result_display",
            "analyte", "result_value", "limit_value", "valid_until",
            "parameters_json", "certificate_url", "note", "status", "status_display",
            "void_reason", "voided_by", "voided_at", "created_by", "created_at",
        ]
        read_only_fields = fields


class LabTestCreateSerializer(serializers.Serializer):
    """Tạo kết quả kiểm nghiệm (BR-12: result phải là PASS/FAIL)."""
    tested_date = serializers.DateField()
    lab_name = serializers.CharField(max_length=200)
    result = serializers.ChoiceField(choices=LabTest.Result.choices)  # BR-12
    analyte = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    result_value = serializers.DecimalField(
        max_digits=10, decimal_places=4, required=False, allow_null=True, default=None
    )
    limit_value = serializers.DecimalField(
        max_digits=10, decimal_places=4, required=False, allow_null=True, default=None
    )
    valid_until = serializers.DateField(required=False, allow_null=True, default=None)
    parameters_json = serializers.JSONField(required=False, default=dict)
    certificate_url = serializers.URLField(required=False, allow_blank=True, default="")
    note = serializers.CharField(required=False, allow_blank=True, default="")

