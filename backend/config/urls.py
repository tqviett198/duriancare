from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/v1/", include("accounts.urls")),
    path("api/v1/", include("catalog.urls")),
    path("api/v1/", include("farms.urls")),
    path("api/v1/", include("logs.urls")),
    path("api/v1/", include("finance.urls")),
    path("api/v1/", include("harvests.urls")),
    path("api/v1/", include("sales.urls")),
    path("api/v1/", include("reports.urls")),
    path("api/v1/", include("tasks.urls")),
]

