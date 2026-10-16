"""Định dạng lỗi thống nhất: {"code", "detail", "fields"} (+ trường phụ nếu có)."""
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.views import exception_handler as drf_exception_handler


class DomainError(APIException):
    """Lỗi nghiệp vụ có mã máy đọc được và dữ liệu phụ (ví dụ danh sách cảnh báo)."""

    def __init__(self, code, detail, status_code=status.HTTP_400_BAD_REQUEST, **extra):
        super().__init__(detail=detail, code=code)
        self.status_code = status_code
        self.code_str = code
        self.extra = extra


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    data = response.data
    if isinstance(exc, DomainError):
        response.data = {"code": exc.code_str, "detail": str(exc.detail), "fields": {}, **exc.extra}
    elif isinstance(exc, ValidationError):
        fields, detail = {}, "Dữ liệu không hợp lệ."
        if isinstance(data, dict):
            data = dict(data)
            non_field = data.pop("non_field_errors", None)
            fields = data
            if non_field:
                detail = "; ".join(str(m) for m in non_field)
        elif isinstance(data, list):
            detail = "; ".join(str(m) for m in data)
        response.data = {"code": "validation_error", "detail": detail, "fields": fields}
    elif isinstance(exc, APIException):
        detail = data.get("detail") if isinstance(data, dict) else data
        response.data = {"code": getattr(exc, "default_code", "error"), "detail": str(detail), "fields": {}}
    return response
