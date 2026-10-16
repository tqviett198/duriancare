from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """username = số điện thoại (quyết định đăng nhập bằng SĐT, xem mục 22 đặc tả)."""

    phone = models.CharField(max_length=20, unique=True)
    full_name = models.CharField(max_length=150)

    def __str__(self):
        return f"{self.full_name} ({self.phone})"
