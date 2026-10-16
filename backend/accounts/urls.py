from django.urls import path

from . import views

urlpatterns = [
    path("auth/register/", views.RegisterView.as_view()),
    path("auth/login/", views.LoginView.as_view()),
    path("auth/refresh/", views.RefreshView.as_view()),
    path("auth/me/", views.MeView.as_view()),
]
