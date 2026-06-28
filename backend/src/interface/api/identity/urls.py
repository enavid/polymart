"""URL patterns for the identity/auth slice."""

from __future__ import annotations

from django.urls import path

from src.interface.api.identity.views import (
    LoginView,
    LogoutView,
    MeView,
    PasswordResetView,
    RefreshView,
    RegisterView,
    RequestOtpView,
)

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/refresh/", RefreshView.as_view(), name="auth-refresh"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("auth/otp/request/", RequestOtpView.as_view(), name="auth-otp-request"),
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/password-reset/", PasswordResetView.as_view(), name="auth-password-reset"),
]
