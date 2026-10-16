from decimal import Decimal

from rest_framework import serializers

from common.permissions import FarmScopedField
from farms.models import Season
from harvests.models import BatchStock

from .models import Buyer, Payment, Sale, SaleLine


# ─────────────────────────────────────────────────────────────────────────────
# Buyer serializers
# ─────────────────────────────────────────────────────────────────────────────

class BuyerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Buyer
        fields = [
            "id", "name", "phone", "address", "tax_code",
            "is_export", "note", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class BuyerCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    address = serializers.CharField(required=False, allow_blank=True, default="")
    tax_code = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    is_export = serializers.BooleanField(required=False, default=False)
    note = serializers.CharField(required=False, allow_blank=True, default="")


# ─────────────────────────────────────────────────────────────────────────────
# Read serializers
# ─────────────────────────────────────────────────────────────────────────────

class SaleLineSerializer(serializers.ModelSerializer):
    batch_code = serializers.CharField(source="stock.batch.batch_code", read_only=True)
    grade = serializers.CharField(source="stock.grade", read_only=True)

    class Meta:
        model = SaleLine
        fields = [
            "id", "stock", "batch_code", "grade",
            "qty_kg", "unit_price", "line_total",
        ]
        read_only_fields = fields


class PaymentSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id", "amount", "payment_date", "method",
            "reference", "note", "status", "status_display",
            "void_reason", "voided_by", "voided_at",
            "created_by", "created_at",
        ]
        read_only_fields = fields


class SaleSerializer(serializers.ModelSerializer):
    """Serializer đọc chi tiết phiếu bán."""
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    payment_status_display = serializers.CharField(
        source="get_payment_status_display", read_only=True,
    )
    buyer_detail = BuyerSerializer(source="buyer", read_only=True)
    lines = SaleLineSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Sale
        fields = [
            "id", "farm", "sale_code", "sale_date",
            "buyer", "buyer_detail",
            "customer_name", "customer_phone",
            "season", "destination",
            "total_amount", "paid_amount",
            "payment_status", "payment_status_display",
            "status", "status_display",
            "note", "lines", "payments",
            "created_by", "created_at", "updated_at",
        ]
        read_only_fields = fields


# ─────────────────────────────────────────────────────────────────────────────
# Write serializers
# ─────────────────────────────────────────────────────────────────────────────

class SaleLineInputSerializer(serializers.Serializer):
    """Dữ liệu một dòng bán (write-only)."""
    stock_id = FarmScopedField(
        queryset=BatchStock.objects.all(),
        farm_lookup="batch__farm_id",
    )
    qty_kg = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.01"),
    )
    unit_price = serializers.DecimalField(
        max_digits=10, decimal_places=0, min_value=Decimal("0"),
    )

    def validate_stock_id(self, stock):
        """Chuyển object BatchStock về dict {stock_id: int} cho service."""
        return stock.id


class SaleCreateSerializer(serializers.Serializer):
    """Tạo phiếu bán – validate input trước khi gọi service."""
    sale_code = serializers.CharField(max_length=50)
    sale_date = serializers.DateField()
    buyer = FarmScopedField(
        queryset=Buyer.objects.all(),
        required=False, allow_null=True, default=None,
    )
    customer_name = serializers.CharField(max_length=200)
    customer_phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    season = FarmScopedField(
        queryset=Season.objects.all(),
        required=False, allow_null=True, default=None,
    )
    destination = serializers.ChoiceField(
        choices=["DOMESTIC", "EXPORT"], required=False, default="DOMESTIC",
    )
    lines = SaleLineInputSerializer(many=True, min_length=1)
    note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_lines(self, value):
        stock_ids = [l["stock_id"] for l in value]
        if len(stock_ids) != len(set(stock_ids)):
            raise serializers.ValidationError("Không được có hai dòng cùng tồn kho trong một phiếu.")
        return value


class PaymentCreateSerializer(serializers.Serializer):
    """Thêm khoản thanh toán."""
    amount = serializers.DecimalField(
        max_digits=14, decimal_places=0, min_value=Decimal("1"),
    )
    payment_date = serializers.DateField()
    method = serializers.CharField(max_length=20, default="CASH")
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    note = serializers.CharField(required=False, allow_blank=True, default="")
