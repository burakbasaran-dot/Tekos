from django.urls import path

from . import views
from . import views_platform

urlpatterns = [
    path("health/", views.health, name="health"),
]

platform_urlpatterns = [
    path("company/select/", views_platform.company_select, name="company_select"),
]
