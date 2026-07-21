from django.urls import path

from . import views
from . import views_platform
from . import views_setup

urlpatterns = [
    path("health/", views.health, name="health"),
]

platform_urlpatterns = [
    path("company/select/", views_platform.company_select, name="company_select"),
    path("subscription/", views_platform.subscription_status, name="subscription_status"),
    path("setup/", views_setup.setup_wizard, {"step": 1}, name="setup_wizard"),
    path("setup/<int:step>/", views_setup.setup_wizard, name="setup_wizard_step"),
]
