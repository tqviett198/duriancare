from django.contrib.auth import get_user_model
from rest_framework import serializers

from common.permissions import FarmScopedField

from .models import Farm, FarmMembership, PlantingCode, Plot, PlotSeason, Season

User = get_user_model()


class FarmSerializer(serializers.ModelSerializer):
    my_role = serializers.SerializerMethodField()

    class Meta:
        model = Farm
        fields = ["id", "name", "address_text", "province", "latitude", "longitude",
                  "area_ha", "note", "my_role", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_my_role(self, farm) -> str:
        user = self.context["request"].user
        return next((m.role for m in farm.memberships.all() if m.user_id == user.id), None)

    def validate_area_ha(self, value):
        if value <= 0:
            raise serializers.ValidationError("Diện tích phải lớn hơn 0.")
        return value


class MembershipSerializer(serializers.ModelSerializer):
    phone = serializers.CharField(write_only=True, required=False)
    user_phone = serializers.CharField(source="user.phone", read_only=True)
    user_name = serializers.CharField(source="user.full_name", read_only=True)

    class Meta:
        model = FarmMembership
        fields = ["id", "phone", "user_phone", "user_name", "role"]

    def validate(self, attrs):
        phone = attrs.pop("phone", None)
        if self.instance is None:   # thêm thành viên mới theo số điện thoại
            user = User.objects.filter(phone=phone).first() if phone else None
            if user is None:
                raise serializers.ValidationError({"phone": ["Chưa có tài khoản với số điện thoại này."]})
            if FarmMembership.objects.filter(farm_id=self.context["farm_id"], user=user).exists():
                raise serializers.ValidationError({"phone": ["Người này đã là thành viên của vườn."]})
            attrs["user"] = user
        return attrs


class PlantingCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlantingCode
        fields = ["id", "code", "target_market", "issued_date", "status", "note"]

    def validate_code(self, value):
        qs = PlantingCode.objects.filter(farm_id=self.context["farm_id"], code=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Mã số này đã có trong vườn.")
        return value


class PlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plot
        fields = ["id", "name", "variety", "area_ha", "tree_count", "planting_date",
                  "growth_stage", "note", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_name(self, value):
        qs = Plot.objects.filter(farm_id=self.context["farm_id"], name=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Tên lô đã tồn tại trong vườn.")
        return value

    def validate_area_ha(self, value):
        if value <= 0:
            raise serializers.ValidationError("Diện tích phải lớn hơn 0.")
        return value


class SeasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Season
        fields = ["id", "name", "start_date", "end_date", "status"]
        read_only_fields = ["id", "status"]   # đổi trạng thái qua /activate/ và /close/

    def validate(self, attrs):
        if self.instance and self.instance.status == Season.Status.CLOSED:
            raise serializers.ValidationError("Vụ đã đóng (CLOSED), không được sửa thông tin.")
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError("Ngày kết thúc phải sau hoặc bằng ngày bắt đầu.")
        return attrs


class PlotSeasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlotSeason
        fields = ["flower_induction_date", "fruit_set_date", "expected_harvest_date", "note"]

    def validate(self, attrs):
        # BR-21: ra hoa < đậu trái < dự kiến thu hoạch (khi có đủ)
        cur = self.instance
        get = lambda k: attrs.get(k, getattr(cur, k, None))
        dates = [get("flower_induction_date"), get("fruit_set_date"), get("expected_harvest_date")]
        present = [d for d in dates if d is not None]
        if any(a >= b for a, b in zip(present, present[1:])):
            raise serializers.ValidationError(
                "Thứ tự ngày phải là: xử lý ra hoa < đậu trái < dự kiến thu hoạch.")
        return attrs
