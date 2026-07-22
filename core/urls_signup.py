"""Signup URL patterns."""

from django.urls import path

from core import views_signup

signup_urlpatterns = [
    path("trial/register/", views_signup.trial_register, name="signup_trial"),
    path("trial/pending/", views_signup.trial_pending, name="signup_trial_pending"),
    path("developer/register/", views_signup.developer_register, name="signup_developer"),
    path(
        "developer/pending/",
        views_signup.developer_pending,
        name="signup_developer_pending",
    ),
    path(
        "verify-email/<str:token>/",
        views_signup.verify_email,
        name="signup_verify_email",
    ),
]

legal_urlpatterns = [
    path("kvkk/", views_signup.legal_kvkk, name="legal_kvkk"),
    path("terms/", views_signup.legal_terms, name="legal_terms"),
]
