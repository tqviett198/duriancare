"""Phân quyền theo vườn (BR-01, BR-02). Quyền thật nằm ở backend."""
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.permissions import SAFE_METHODS, BasePermission

OWNER, WORKER, ADVISOR = "OWNER", "WORKER", "ADVISOR"
ALL_ROLES = (OWNER, WORKER, ADVISOR)


class FarmRolePermission(BasePermission):
    """Người dùng phải là thành viên của farm_id trên URL và có vai trò đủ quyền cho thao tác."""

    message = "Bạn không có quyền với vườn này."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        from farms.models import FarmMembership

        role = (FarmMembership.objects
                .filter(farm_id=view.kwargs["farm_id"], user=request.user)
                .values_list("role", flat=True).first())
        request.farm_role = role
        return role in view.get_allowed_roles(request)


class FarmScopedMixin:
    """Mọi view dạng /farms/{farm_id}/... dùng mixin này."""

    permission_classes = [FarmRolePermission]
    roles_read = ALL_ROLES
    roles_write = (OWNER,)
    roles_by_action = {}
    farm_field = "farm_id"          # đường lọc queryset theo vườn

    def get_allowed_roles(self, request):
        action = getattr(self, "action", None)
        if action in self.roles_by_action:
            return self.roles_by_action[action]
        return self.roles_read if request.method in SAFE_METHODS else self.roles_write

    @property
    def farm(self):
        if not hasattr(self, "_farm"):
            from farms.models import Farm
            self._farm = get_object_or_404(Farm, pk=self.kwargs["farm_id"])
        return self._farm

    def get_queryset(self):
        return super().get_queryset().filter(**{self.farm_field: self.kwargs["farm_id"]})

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["farm_id"] = int(self.kwargs["farm_id"])
        return ctx


class FarmScopedField(serializers.PrimaryKeyRelatedField):
    """Khóa ngoại chỉ chấp nhận bản ghi thuộc vườn trên URL (BR-02)."""

    default_error_messages = {
        "does_not_exist": "Không tìm thấy trong vườn này (id={pk_value}).",
    }

    def __init__(self, farm_lookup="farm_id", allow_global=False, **kwargs):
        self.farm_lookup = farm_lookup
        self.allow_global = allow_global
        super().__init__(**kwargs)

    def get_queryset(self):
        from django.db.models import Q

        qs = super().get_queryset()
        fid = self.context["farm_id"]
        cond = Q(**{self.farm_lookup: fid})
        if self.allow_global:
            cond |= Q(**{self.farm_lookup: None})
        return qs.filter(cond)
