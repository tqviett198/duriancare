import re

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

User = get_user_model()
PHONE_RE = re.compile(r"^0\d{9}$")


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["id", "phone", "full_name", "email", "password"]

    def validate_phone(self, value):
        if not PHONE_RE.match(value):
            raise serializers.ValidationError("Số điện thoại gồm 10 chữ số, bắt đầu bằng 0.")
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError("Số điện thoại đã được đăng ký.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated):
        return User.objects.create_user(username=validated["phone"], **validated)


class MeSerializer(serializers.ModelSerializer):
    farms = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "phone", "full_name", "email", "farms"]

    def get_farms(self, user) -> list:
        return [{"id": m.farm_id, "name": m.farm.name, "role": m.role}
                for m in user.memberships.select_related("farm")]
