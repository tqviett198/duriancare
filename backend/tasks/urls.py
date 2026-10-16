from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import TaskViewSet, NotificationViewSet

_task_router = SimpleRouter()
_task_router.register("", TaskViewSet, basename="task")

_notif_router = SimpleRouter()
_notif_router.register("", NotificationViewSet, basename="notification")

urlpatterns = [
    path("farms/<int:farm_id>/tasks/", include(_task_router.urls)),
    path("farms/<int:farm_id>/notifications/", include(_notif_router.urls)),
]
