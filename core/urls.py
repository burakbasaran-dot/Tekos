from django.urls import path

from . import views
from . import views_management
from . import views_platform
from . import views_setup

urlpatterns = [
    path("health/", views.health, name="health"),
]

platform_urlpatterns = [
    path("company/select/", views_platform.company_select, name="company_select"),
    path("companies/", views_management.company_list, name="company_list"),
    path("demo-companies/", views_management.demo_company_list, name="demo_company_list"),
    path("system-health/", views_management.system_health, name="system_health"),
    path("audit-logs/", views_management.audit_log_list, name="audit_log_list"),
    path("subscription/", views_platform.subscription_status, name="subscription_status"),
    path("setup/", views_setup.setup_wizard, {"step": 1}, name="setup_wizard"),
    path("setup/<int:step>/", views_setup.setup_wizard, name="setup_wizard_step"),
]
